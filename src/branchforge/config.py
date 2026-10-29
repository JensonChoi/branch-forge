from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMConfig(Settings):
    provider: str = "fake"
    model: str = "openai/gpt-4o-mini"
    max_output_tokens: int = Field(default=2048, gt=0)
    max_prompt_chars: int = Field(default=16000, ge=1000)
    temperature: float | None = None
    timeout_seconds: float = Field(default=60, gt=0)
    retries: int = Field(default=2, ge=0)
    max_concurrent_requests: int = Field(default=4, gt=0)


class BudgetConfig(Settings):
    max_llm_calls: int = Field(default=60, gt=0)
    max_candidates: int = Field(default=60, gt=0)
    max_tokens: int | None = Field(default=300000, gt=0)
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_wall_time_seconds: float = Field(default=300, gt=0)


class AgentConfig(Settings):
    max_concurrent: int = Field(default=4, gt=0)
    max_candidates_per_task: int = Field(default=3, gt=0)
    max_refinement_steps: int = Field(default=2, ge=0)
    max_llm_calls: int = Field(default=5, gt=0)
    max_wall_time_seconds: float = Field(default=90, gt=0)


class BeamConfig(Settings):
    beam_width: int = Field(default=4, gt=0)
    branching_factor: int = Field(default=3, gt=0)
    max_depth: int = Field(default=6, gt=0)
    max_frontier_iterations: int = Field(default=4, gt=0)


class MCTSConfig(Settings):
    exploration_constant: float = Field(default=1.414, ge=0)
    max_simulations: int = Field(default=30, gt=0)
    branching_factor: int = Field(default=3, gt=0)
    max_depth: int = Field(default=5, gt=0)


class ExecutionConfig(Settings):
    image: str = "python:3.12-slim"
    max_concurrent_containers: int = Field(default=4, gt=0)
    output_limit_bytes: int = Field(default=65536, gt=0)
    cpus: float = Field(default=1, gt=0)
    pids_limit: int = Field(default=32, gt=0)


class Config(Settings):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    beam_search: BeamConfig = Field(default_factory=BeamConfig)
    mcts: MCTSConfig = Field(default_factory=MCTSConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    best_of_n: int = Field(default=10, gt=0)
    runs_dir: Path = Path("runs")
    seed: int = 0


def load_config(path: Path | None) -> Config:
    return Config.model_validate(yaml.safe_load(path.read_text()) or {}) if path else Config()
