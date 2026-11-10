import asyncio
import json

import pytest

from branchforge.config import LLMConfig
from branchforge.experiments.spending import SpendingClient, SpendLimitExceeded
from branchforge.llm import GenerationResult


async def test_concurrent_requests_cannot_oversubscribe(tmp_path):
    class Client:
        calls = 0

        async def generate(self, messages, config):
            self.calls += 1
            await asyncio.sleep(0.01)
            return GenerationResult(content="", input_tokens=10, output_tokens=10, cost_usd=0.00002)

    underlying = Client()
    guarded = SpendingClient(underlying, tmp_path / "ledger.json", 0.01, 1, 1)
    config = LLMConfig(max_output_tokens=1000)
    results = await asyncio.gather(
        *(guarded.generate([{"role": "user", "content": "test"}], config) for _ in range(3)),
        return_exceptions=True,
    )
    assert underlying.calls == 1
    assert sum(isinstance(r, SpendLimitExceeded) for r in results) == 2
    assert sum(r["accounted_micro_usd"] for r in guarded.state["requests"]) <= 10000
    assert guarded.exhausted


async def test_failed_request_retains_reservation_across_resume(tmp_path):
    class Client:
        async def generate(self, messages, config):
            raise TimeoutError("unknown billing")

    path = tmp_path / "ledger.json"
    guarded = SpendingClient(Client(), path, 0.01, 1, 1)
    with pytest.raises(TimeoutError):
        await guarded.generate(
            [{"role": "user", "content": "test"}], LLMConfig(max_output_tokens=1000)
        )
    entry = json.loads(path.read_text())["requests"][0]
    assert entry["accounted_micro_usd"] == entry["reserved_micro_usd"]
    resumed = SpendingClient(Client(), path, 0.01, 1, 1)
    with pytest.raises(SpendLimitExceeded):
        await resumed.generate(
            [{"role": "user", "content": "test"}], LLMConfig(max_output_tokens=1000)
        )


async def test_returned_usage_releases_unused_reservation(tmp_path):
    class Client:
        async def generate(self, messages, config):
            return GenerationResult(
                content="", input_tokens=100, output_tokens=200, cost_usd=0.0003
            )

    guarded = SpendingClient(Client(), tmp_path / "ledger.json", 0.01, 1, 1)
    for _ in range(4):
        await guarded.generate([], LLMConfig(max_output_tokens=1000))
    assert sum(r["accounted_micro_usd"] for r in guarded.state["requests"]) == 1200


def test_reduced_stage_schedule():
    from branchforge.experiments.runner import ExperimentConfig, preflight

    config = ExperimentConfig(variants=("baseline",), stage="validation")
    config.search.budget.max_llm_calls = 8
    assert preflight(config, 20)["trials"] == 20
    assert preflight(config, 20)["physical_request_ceiling"] == 160
    with pytest.raises(ValueError):
        ExperimentConfig(variants=("baseline", "baseline"))


async def test_credit_exhaustion_stops_future_requests(tmp_path):
    from branchforge.llm import ProviderCreditExhausted

    class Client:
        calls = 0

        async def generate(self, messages, config):
            self.calls += 1
            raise ProviderCreditExhausted("API_CREDIT_EXHAUSTED")

    client = Client()
    guarded = SpendingClient(client, tmp_path / "ledger.json", 1, 1, 1)
    with pytest.raises(ProviderCreditExhausted):
        await guarded.generate([], LLMConfig(max_output_tokens=1000))
    with pytest.raises(SpendLimitExceeded):
        await guarded.generate([], LLMConfig(max_output_tokens=1000))
    assert client.calls == 1
    assert guarded.state["stop_reason"] == "API_CREDIT_EXHAUSTED"


async def test_unlimited_mode_retains_accounting(tmp_path):
    class Client:
        async def generate(self, messages, config):
            return GenerationResult(
                content="", input_tokens=1, output_tokens=1000, cost_usd=0.001001
            )

    guarded = SpendingClient(Client(), tmp_path / "ledger.json", None, 1, 1)
    for _ in range(3):
        await guarded.generate([], LLMConfig(max_output_tokens=1000))
    assert guarded.state["limit_micro_usd"] is None
    assert len(guarded.state["requests"]) == 3
    assert sum(r["accounted_micro_usd"] for r in guarded.state["requests"]) == 3003
    assert not guarded.exhausted
