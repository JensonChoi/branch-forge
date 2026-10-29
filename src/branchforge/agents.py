import asyncio
import time
from typing import Protocol

from .config import Config
from .execution import Evaluator
from .llm import Generation, LLMClient, messages
from .models import BranchResult, BranchTask, Candidate, CandidateResult, HistoryEntry
from .runtime import Budget, Events, Limiter


class BranchAgent(Protocol):
    async def explore(self, task: BranchTask) -> BranchResult: ...


class CodingAgent:
    def __init__(
        self,
        config: Config,
        client: LLMClient,
        evaluator: Evaluator,
        budget: Budget,
        events: Events,
    ):
        self.config, self.client, self.evaluator = config, client, evaluator
        self.budget, self.events = budget, events
        self.llm_slots = Limiter(config.llm.max_concurrent_requests)
        self.results: dict[str, BranchResult] = {}

    async def explore(self, task: BranchTask) -> BranchResult:
        started = time.monotonic()
        result = BranchResult(task_id=task.task_id, parent_node_id=task.parent_node_id)
        self.results[task.task_id] = result
        history = list(task.history)
        self.events.emit("SUBAGENT_STARTED", task_id=task.task_id, worker_id=task.task_id)
        try:
            async with asyncio.timeout(task.max_wall_time_seconds):
                for step in range(task.max_candidates):
                    if step:
                        self.events.emit("SUBAGENT_REFINEMENT_STARTED", task_id=task.task_id)
                    generated = None
                    for attempt in range(self.config.llm.retries + 1):
                        prompt = messages(task, history, self.config.llm.max_prompt_chars)
                        await self.budget.consume_call(task.task_id)
                        result.llm_calls += 1
                        self.events.emit(
                            "SUBAGENT_LLM_REQUESTED", task_id=task.task_id, attempt=attempt
                        )
                        try:
                            async with self.llm_slots:
                                async with asyncio.timeout(self.config.llm.timeout_seconds):
                                    response = await self.client.generate(prompt, self.config.llm)
                            self.budget.usage(
                                task.task_id,
                                response.input_tokens,
                                response.output_tokens,
                                response.cost_usd,
                            )
                            result.input_tokens += response.input_tokens
                            result.output_tokens += response.output_tokens
                            generated = Generation.model_validate_json(response.content)
                            break
                        except (ValueError, TimeoutError, RuntimeError) as exc:
                            if attempt == self.config.llm.retries:
                                raise RuntimeError(f"Generation failed: {exc}") from exc
                    assert generated is not None
                    self.budget.consume_candidate(task.task_id)
                    candidate = Candidate(
                        candidate_id=f"{task.task_id}-c{step}",
                        parent_candidate_id=history[-1].candidate.candidate_id if history else None,
                        **generated.model_dump(),
                    )
                    record = CandidateResult(
                        candidate=candidate, evaluation=None, refinement_step=step
                    )
                    result.candidates.append(record)
                    self.events.emit(
                        "CANDIDATE_GENERATED",
                        task_id=task.task_id,
                        candidate_id=candidate.candidate_id,
                    )
                    evaluation = await self.evaluator.evaluate(candidate, task.problem)
                    self.budget.evaluations += 1
                    result.candidates[-1] = record.model_copy(update={"evaluation": evaluation})
                    self.events.emit(
                        "CANDIDATE_EVALUATED",
                        task_id=task.task_id,
                        candidate_id=candidate.candidate_id,
                        reward=evaluation.reward,
                    )
                    history.append(HistoryEntry(candidate=candidate, evaluation=evaluation))
                    if evaluation.reward is None:
                        raise RuntimeError(evaluation.error)
                    if evaluation.reward == 1:
                        break
        except asyncio.CancelledError:
            result.status = "CANCELED"
            result.error = "Canceled"
            raise
        except Exception as exc:  # noqa: BLE001 -- worker failures are returned and persisted
            result.status = "FAILED"
            result.error = str(exc)
        finally:
            result.elapsed_seconds = time.monotonic() - started
            self.events.emit(
                "SUBAGENT_" + ("FINISHED" if result.status == "COMPLETED" else result.status),
                task_id=task.task_id,
                elapsed_seconds=result.elapsed_seconds,
                error=result.error,
            )
        return result


class BranchWorkerPool:
    def __init__(self, concurrency: int, agent: CodingAgent, events: Events):
        self.concurrency, self.agent, self.events = concurrency, agent, events
        self.slots = Limiter(concurrency)
        self.queue_waits: list[float] = []
        self.active_seconds = 0.0

    async def run(self, tasks: list[BranchTask]) -> list[BranchResult]:
        # Only concurrency worker coroutines exist, regardless of frontier size.
        iterator = iter(tasks)
        queued = time.monotonic()
        for task in tasks:
            self.events.emit("BRANCH_TASK_QUEUED", task_id=task.task_id)

        async def worker() -> None:
            for task in iterator:
                async with self.slots:
                    started = time.monotonic()
                    self.queue_waits.append(started - queued)
                    try:
                        await self.agent.explore(task)
                    finally:
                        self.active_seconds += time.monotonic() - started

        async with asyncio.TaskGroup() as group:
            for _ in range(min(self.concurrency, len(tasks))):
                group.create_task(worker())
        return [self.agent.results[t.task_id] for t in tasks]
