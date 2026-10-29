import asyncio
import json
import time
from pathlib import Path
from typing import Any, Self

from .config import Config
from .models import BranchTask, now


class BudgetExceeded(Exception):
    pass


class Events:
    def __init__(self, directory: Path, run_id: str):
        directory.mkdir(parents=True, exist_ok=False)
        self.directory = directory
        self.run_id = run_id
        self.sequence = 0

    def emit(self, event_type: str, **metadata: Any) -> None:
        self.sequence += 1
        event = dict(
            run_id=self.run_id,
            timestamp=now().isoformat(),
            event_type=event_type,
            sequence=self.sequence,
            **metadata,
        )
        with (self.directory / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(event, default=str) + "\n")

    def save(self, name: str, data: Any) -> None:
        target = self.directory / name
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2, default=str))
        temporary.replace(target)


class Budget:
    """Reserve deterministic task quotas before concurrent dispatch."""

    def __init__(self, config: Config, events: Events):
        self.config = config
        self.events = events
        self.started = time.monotonic()
        self.calls = self.candidates = self.input_tokens = self.output_tokens = 0
        self.evaluations = 0
        self.cost_usd = 0.0
        self.cost_known = True
        self.reserved_calls = self.reserved_candidates = self.reserved_tokens = 0
        self.quotas: dict[str, dict[str, int]] = {}
        self.reason: str | None = None
        self.lock = asyncio.Lock()
        if config.budget.max_cost_usd is not None:
            raise ValueError("Hard cost limits require reliable pre-request pricing; unsupported")
        if config.llm.provider != "fake" and config.budget.max_tokens is not None:
            raise ValueError(
                "Set budget.max_tokens: null for real providers: no guaranteed tokenizer bound"
            )

    def reserve(self, task_id: str, candidates: int, calls: int) -> tuple[int, int] | None:
        cfg = self.config.budget
        candidates = min(
            candidates, cfg.max_candidates - self.candidates - self.reserved_candidates
        )
        calls = min(calls, cfg.max_llm_calls - self.calls - self.reserved_calls)
        per_call = self.config.llm.max_prompt_chars + self.config.llm.max_output_tokens
        if cfg.max_tokens is not None:
            calls = min(
                calls,
                (cfg.max_tokens - self.input_tokens - self.output_tokens - self.reserved_tokens)
                // per_call,
            )
        if candidates <= 0:
            self.reason = "MAX_CANDIDATES"
            return None
        if calls <= 0:
            self.reason = (
                "MAX_LLM_CALLS"
                if self.calls + self.reserved_calls >= cfg.max_llm_calls
                else "MAX_TOKENS"
            )
            return None
        self.quotas[task_id] = {
            "candidates": candidates,
            "calls": calls,
            "tokens": calls * per_call,
        }
        self.reserved_candidates += candidates
        self.reserved_calls += calls
        self.reserved_tokens += calls * per_call
        self.events.emit(
            "BUDGET_RESERVATION_CREATED", task_id=task_id, candidates=candidates, calls=calls
        )
        return candidates, calls

    async def consume_call(self, task_id: str) -> None:
        async with self.lock:
            quota = self.quotas[task_id]
            if quota["calls"] <= 0:
                raise BudgetExceeded("MAX_LLM_CALLS")
            quota["calls"] -= 1
            self.reserved_calls -= 1
            self.calls += 1

    def consume_candidate(self, task_id: str) -> None:
        quota = self.quotas[task_id]
        if quota["candidates"] <= 0:
            raise BudgetExceeded("MAX_CANDIDATES")
        quota["candidates"] -= 1
        self.reserved_candidates -= 1
        self.candidates += 1

    def usage(
        self, task_id: str, input_tokens: int, output_tokens: int, cost_usd: float | None = None
    ) -> None:
        if cost_usd is None and self.config.llm.provider != "fake":
            self.cost_known = False
        elif cost_usd is not None:
            self.cost_usd += cost_usd
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        per_call = self.config.llm.max_prompt_chars + self.config.llm.max_output_tokens
        self.quotas[task_id]["tokens"] -= per_call
        self.reserved_tokens -= per_call

    def release(self, task: BranchTask) -> None:
        quota = self.quotas.pop(task.task_id)
        self.reserved_calls -= quota["calls"]
        self.reserved_candidates -= quota["candidates"]
        self.reserved_tokens -= quota["tokens"]
        self.events.emit("BUDGET_RESERVATION_RECONCILED", task_id=task.task_id)

    def summary(self) -> dict[str, Any]:
        return {
            "llm_calls": self.calls,
            "candidates": self.candidates,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "evaluations": self.evaluations,
            "elapsed_seconds": time.monotonic() - self.started,
            "cost_usd": self.cost_usd if self.cost_known else None,
        }


class Limiter:
    def __init__(self, limit: int):
        self.semaphore = asyncio.BoundedSemaphore(limit)
        self.active = self.maximum = 0
        self.active_seconds = 0.0
        self.started = time.monotonic()
        self.entries: list[float] = []

    async def __aenter__(self) -> Self:
        await self.semaphore.acquire()
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        return self

    async def __aexit__(self, *args: object) -> None:
        self.active -= 1
        self.semaphore.release()
