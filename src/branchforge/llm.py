import asyncio
import json
from typing import Protocol

from pydantic import BaseModel

from .config import LLMConfig
from .models import BranchTask, HistoryEntry


class Generation(BaseModel):
    strategy: str | None = None
    explanation: str
    code: str


class GenerationResult(BaseModel):
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None


class LLMClient(Protocol):
    async def generate(
        self, messages: list[dict[str, str]], config: LLMConfig
    ) -> GenerationResult: ...


def messages(task: BranchTask, history: list[HistoryEntry], limit: int) -> list[dict[str, str]]:
    problem = task.problem.model_dump_json()
    base = "Return JSON with strategy, explanation, code. Write a Python stdin/stdout solution.\n"
    base += problem + "\nOptional strategy: " + str(task.strategy_hint)
    if len(base) > limit:
        raise ValueError("Problem exceeds prompt size limit")
    tail = ""
    for entry in reversed(history):
        item = "\nAncestor and visible feedback:\n" + entry.model_dump_json()
        if len(base) + len(tail) + len(item) > limit:
            break
        tail = item + tail
    return [{"role": "user", "content": base + tail}]


class LiteLLMClient:
    async def generate(self, messages: list[dict[str, str]], config: LLMConfig) -> GenerationResult:
        import litellm

        kwargs = {
            "model": config.model,
            "messages": messages,
            "max_tokens": config.max_output_tokens,
            "timeout": config.timeout_seconds,
            "num_retries": 0,
        }
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        try:
            response = await litellm.acompletion(**kwargs)
        except litellm.exceptions.OpenAIError as exc:
            raise RuntimeError(f"Provider request failed: {type(exc).__name__}") from exc
        usage = response.usage
        if usage is None:
            raise ValueError("Provider omitted token usage")
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:  # noqa: BLE001 -- pricing is optional; unknown remains explicit
            cost = None
        return GenerationResult(
            cost_usd=cost,
            content=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )


class FakeLLM:
    """Scripted sequences are keyed by strategy, never by arrival order."""

    def __init__(self, scripts: dict[str, list[str | Exception]] | None = None):
        self.scripts = scripts
        self.seen: list[list[dict[str, str]]] = []

    async def generate(self, messages: list[dict[str, str]], config: LLMConfig) -> GenerationResult:
        await asyncio.sleep(0)
        self.seen.append([dict(m) for m in messages])
        prompt = messages[-1]["content"]
        hint = prompt.split("Optional strategy: ", 1)[1].split("\n", 1)[0]
        step = prompt.count("Ancestor and visible feedback:")
        if self.scripts is not None:
            sequence = self.scripts.get(hint, self.scripts.get("default", []))
            if not sequence:
                raise ValueError("No scripted response")
            item = sequence[min(step, len(sequence) - 1)]
            if isinstance(item, Exception):
                raise item
            code = item
        else:
            from .references import REFERENCES

            problem_id = json.loads(prompt.split("\n", 1)[1].split("\nOptional strategy:")[0])[
                "problem_id"
            ]
            if hint == "Dynamic programming" and step > 0:
                code = REFERENCES[problem_id]
            elif hint == "Dynamic programming" and problem_id == "max_subarray":
                code = "print(4)"
            elif hint == "Alternative approach":
                code = "print(-1)"
            else:
                code = "print(0)"
        content = Generation(
            strategy=hint, explanation="Deterministic test fixture", code=code
        ).model_dump_json()
        return GenerationResult(
            content=content,
            input_tokens=min(len(prompt), config.max_prompt_chars),
            output_tokens=min(len(content), config.max_output_tokens),
        )
