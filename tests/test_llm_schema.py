import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from branchforge.config import LLMConfig
from branchforge.llm import Generation, LiteLLMClient, generation_response_format


def test_strict_generation_schema():
    response_format = generation_response_format()
    schema = response_format["json_schema"]["schema"]
    assert response_format["json_schema"]["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"strategy", "explanation", "code"}
    assert schema["properties"]["strategy"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert (
        Generation.model_validate_json(
            '{"strategy":null,"explanation":"x","code":"print(0)"}'
        ).strategy
        is None
    )
    for payload in (
        {"strategy": ["list"], "explanation": "x", "code": "print(0)"},
        {"strategy": None, "explanation": "x", "code": "print(0)", "extra": True},
        {"strategy": None, "explanation": "x", "code": 123},
    ):
        with pytest.raises(ValidationError):
            Generation.model_validate_json(json.dumps(payload))


async def test_litellm_sends_schema_and_preserves_usage(monkeypatch):
    import litellm

    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, completion_tokens_details=None)
    response = SimpleNamespace(
        usage=usage,
        model="test",
        system_fingerprint=None,
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content='{"strategy":null,"explanation":"x","code":"print(0)"}'
                ),
            )
        ],
    )
    completion = AsyncMock(return_value=response)
    monkeypatch.setattr(litellm, "acompletion", completion)
    monkeypatch.setattr(litellm, "completion_cost", lambda **kwargs: 0.001)
    result = await LiteLLMClient().generate([{"role": "user", "content": "test"}], LLMConfig())
    assert completion.call_args.kwargs["response_format"] == generation_response_format()
    assert result.cost_usd == 0.001
    assert result.output_tokens == 20


async def test_truncated_response_keeps_usage_for_accounting(monkeypatch):
    import litellm

    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=100,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=100),
        ),
        model="test",
        system_fingerprint=None,
        choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content=""))],
    )
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(return_value=response))
    monkeypatch.setattr(litellm, "completion_cost", lambda **kwargs: 0.01)
    result = await LiteLLMClient().generate([], LLMConfig())
    assert result.finish_reason == "length"
    assert result.cost_usd == 0.01
    with pytest.raises(ValidationError):
        Generation.model_validate_json(result.content)


async def test_provider_credit_error_is_classified_without_details(monkeypatch):
    import litellm

    from branchforge.llm import ProviderCreditExhausted

    error = litellm.RateLimitError("private provider details", llm_provider="openai", model="test")
    error.code = "insufficient_quota"
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(side_effect=error))
    with pytest.raises(ProviderCreditExhausted, match="^API_CREDIT_EXHAUSTED$"):
        await LiteLLMClient().generate([], LLMConfig())
