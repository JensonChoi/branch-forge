"""Public dashboard contracts, independent of secret-bearing configuration."""

from typing import Any, TypeVar

from pydantic import BaseModel, Field

from branchforge.models import SearchNode

T = TypeVar("T")


class Envelope[T](BaseModel):
    data: T
    warnings: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    run_id: str
    title: str
    algorithm: str | None = None
    model: str | None = None
    status: str
    termination_reason: str | None = None
    selected_node_id: str | None = None
    visible_reward: float | None = None
    budget: dict[str, float | int | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RunDetail(RunSummary):
    started_at: str | None = None
    held_out_reward: float | None = None
    replay_supported: bool
    detailed_replay: bool


class RunPage(BaseModel):
    items: list[RunSummary]
    total: int


class SearchTreeResponse(BaseModel):
    nodes: dict[str, SearchNode]


class SearchEventResponse(BaseModel):
    sequence: int
    event_type: str
    timestamp: str | None = None
    schema_version: int = 1
    run_id: str | None = None
    node_id: str | None = None
    node_ids: list[str] | None = None
    candidate_id: str | None = None
    task_id: str | None = None
    worker_id: str | None = None
    parent_id: str | None = None
    node: SearchNode | None = None
    root: SearchNode | None = None
    candidate: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    reward: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    frontier_index: int | None = None
    simulation: int | None = None
    duration_seconds: float | None = None
    survivors: list[str] | None = None


class Activity(BaseModel):
    frontier_index: int | None = None
    task_id: str
    worker_id: str
    kind: str
    start: str | None
    end: str | None
    candidate_id: str | None = None
    outcome: str | None = None


class WorkerTimelineResponse(BaseModel):
    intervals: list[Activity]
    peak_concurrency: int | None
    busy_seconds: float | None
    average_active: float | None


class RunMetricsResponse(BaseModel):
    llm_calls: int | None = None
    candidates: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    elapsed_seconds: float | None = None
    max_depth: int
    successful: int
    statuses: dict[str, int]
    frontiers: list[dict[str, int | float | None]] = Field(default_factory=list)
