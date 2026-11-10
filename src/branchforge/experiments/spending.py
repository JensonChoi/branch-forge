"""Durable request admission: unknown or interrupted charges retain their full reservation."""

import asyncio
import json
import math
from pathlib import Path
from typing import Any

from ..config import LLMConfig
from ..llm import GenerationResult, LLMClient, ProviderCreditExhausted, generation_response_format


class SpendLimitExceeded(RuntimeError):
    pass


class SpendingClient:
    def __init__(
        self,
        client: LLMClient,
        path: Path,
        limit: float | None,
        input_rate: float,
        output_rate: float,
    ):
        self.client, self.path = client, path
        self.limit = math.floor(limit * 1_000_000) if limit is not None else None
        self.input_rate, self.output_rate = input_rate, output_rate
        self.lock = asyncio.Lock()
        self.state: dict[str, Any] = (
            json.loads(path.read_text())
            if path.exists()
            else {
                "limit_micro_usd": self.limit,
                "input_usd_per_million": input_rate,
                "output_usd_per_million": output_rate,
                "requests": [],
                "exhausted": False,
            }
        )
        if (
            self.state["limit_micro_usd"] != self.limit
            or self.state["input_usd_per_million"] != input_rate
            or self.state["output_usd_per_million"] != output_rate
        ):
            raise ValueError("Spending ledger configuration changed")

    @property
    def exhausted(self) -> bool:
        return bool(self.state["exhausted"])

    def persist(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2))
        temporary.replace(self.path)

    async def generate(self, messages: list[dict[str, str]], config: LLMConfig) -> GenerationResult:
        # Text-only requests: UTF-8 bytes upper-bound content tokens, plus framing allowance.
        input_bound = (
            len(json.dumps(messages, ensure_ascii=False).encode())
            + len(json.dumps(generation_response_format(), ensure_ascii=False).encode())
            + 4096
        )
        reserve = math.ceil(
            input_bound * self.input_rate + config.max_output_tokens * self.output_rate
        )
        async with self.lock:
            accounted = sum(r["accounted_micro_usd"] for r in self.state["requests"])
            if self.exhausted or (self.limit is not None and accounted + reserve > self.limit):
                self.state["exhausted"] = True
                self.state.setdefault("stop_reason", "EXPERIMENT_SPENDING_LIMIT")
                self.persist()
                raise SpendLimitExceeded("EXPERIMENT_SPENDING_LIMIT")
            entry = {
                "request_index": len(self.state["requests"]),
                "status": "reserved",
                "reserved_micro_usd": reserve,
                "accounted_micro_usd": reserve,
            }
            self.state["requests"].append(entry)
            self.persist()  # Durable before any network dispatch, including on process crashes.
        # Errors/cancellation intentionally retain the maximum possible charge.
        try:
            response = await self.client.generate(messages, config)
        except ProviderCreditExhausted:
            async with self.lock:
                self.state["exhausted"] = True
                self.state["stop_reason"] = "API_CREDIT_EXHAUSTED"
                entry["status"] = "credit_rejected"
                self.persist()
            raise
        usage_bound = math.ceil(
            response.input_tokens * self.input_rate + response.output_tokens * self.output_rate
        )
        if response.cost_usd is not None:
            usage_bound = max(usage_bound, math.ceil(response.cost_usd * 1_000_000))
        async with self.lock:
            entry.update(
                status="returned",
                accounted_micro_usd=usage_bound,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                reported_cost_usd=response.cost_usd,
            )
            if usage_bound > reserve:
                self.state["exhausted"] = True
                self.state["pricing_bound_error"] = True
            self.persist()
        if usage_bound > reserve:
            raise RuntimeError(
                "Provider exceeded configured pricing/token bound; stopping experiment"
            )
        return response
