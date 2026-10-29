from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def uid() -> str:
    return uuid4().hex


def now() -> datetime:
    return datetime.now(UTC)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TestCase(Frozen):
    __test__ = False
    input: str
    expected_output: str


class VisibleProblem(Frozen):
    problem_id: str
    title: str
    statement: str
    input_format: str
    output_format: str
    constraints: str | None = None
    visible_tests: tuple[TestCase, ...] = Field(min_length=1)
    time_limit_seconds: float = Field(default=2, gt=0)
    memory_limit_mb: int = Field(default=256, ge=32)


class CodingProblem(VisibleProblem):
    hidden_tests: tuple[TestCase, ...] = ()

    def visible(self) -> VisibleProblem:
        return VisibleProblem.model_validate(self.model_dump(exclude={"hidden_tests"}))


class Candidate(Frozen):
    candidate_id: str = Field(default_factory=uid)
    parent_candidate_id: str | None = None
    strategy: str | None = None
    explanation: str
    code: str


class TestStatus(StrEnum):
    __test__ = False
    PASS = "PASS"
    WRONG_ANSWER = "WRONG_ANSWER"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"


class TestResult(Frozen):
    __test__ = False
    test_id: str
    status: TestStatus
    expected_output: str
    actual_output: str = ""
    stderr: str = ""
    exit_code: int | None = None
    execution_time_ms: float = 0
    error: str | None = None


class EvaluationResult(Frozen):
    candidate_id: str
    passed_tests: int
    total_tests: int = Field(gt=0)
    reward: float | None = Field(default=None, ge=0, le=1)
    test_results: tuple[TestResult, ...]
    execution_time_ms: float
    error: str | None = None


class NodeStatus(StrEnum):
    PENDING = "PENDING"
    EXPANDING = "EXPANDING"
    EVALUATING = "EVALUATING"
    EVALUATED = "EVALUATED"
    FAILED = "FAILED"
    PRUNED = "PRUNED"


class SearchNode(BaseModel):
    node_id: str
    parent_id: str | None
    depth: int
    children_ids: list[str] = Field(default_factory=list)
    candidate: Candidate | None = None
    evaluation: EvaluationResult | None = None
    visits: int = 0
    total_reward: float = 0
    status: NodeStatus = NodeStatus.PENDING
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    order: int = 0
    worker_id: str | None = None


class SearchTree(BaseModel):
    nodes: dict[str, SearchNode] = Field(
        default_factory=lambda: {"root": SearchNode(node_id="root", parent_id=None, depth=0)}
    )

    @model_validator(mode="after")
    def integrity(self) -> "SearchTree":
        assert "root" in self.nodes
        for key, node in self.nodes.items():
            if key != node.node_id:
                raise ValueError("registry key mismatch")
            if key == "root":
                if node.parent_id is not None or node.depth != 0:
                    raise ValueError("invalid root")
            else:
                parent = self.nodes.get(node.parent_id or "")
                if not parent or parent.depth + 1 != node.depth or key not in parent.children_ids:
                    raise ValueError("invalid ancestry")
            if len(set(node.children_ids)) != len(node.children_ids):
                raise ValueError("duplicate children")
            for child in node.children_ids:
                if child not in self.nodes or self.nodes[child].parent_id != key:
                    raise ValueError("invalid child")
        return self

    def add(
        self,
        parent: str,
        candidate: Candidate,
        evaluation: EvaluationResult | None,
        max_depth: int,
        worker: str | None = None,
    ) -> SearchNode:
        ancestor = self.nodes[parent]
        if ancestor.depth >= max_depth or candidate.candidate_id in self.nodes:
            raise ValueError("depth or duplicate ID violation")
        expected = ancestor.candidate.candidate_id if ancestor.candidate else None
        if candidate.parent_candidate_id != expected:
            raise ValueError("candidate parent mismatch")
        if evaluation and evaluation.candidate_id != candidate.candidate_id:
            raise ValueError("evaluation identity mismatch")
        node = SearchNode(
            node_id=candidate.candidate_id,
            parent_id=parent,
            depth=ancestor.depth + 1,
            candidate=candidate,
            evaluation=evaluation,
            status=NodeStatus.EVALUATED
            if evaluation and evaluation.reward is not None
            else NodeStatus.FAILED,
            order=len(self.nodes),
            worker_id=worker,
        )
        self.nodes[node.node_id] = node
        ancestor.children_ids.append(node.node_id)
        ancestor.updated_at = now()
        return node

    def path(self, node_id: str) -> list[SearchNode]:
        result = []
        node = self.nodes[node_id]
        while True:
            result.append(node)
            if node.parent_id is None:
                return list(reversed(result))
            node = self.nodes[node.parent_id]

    def leaves(self) -> list[SearchNode]:
        return [n for n in self.nodes.values() if not n.children_ids]

    def transition(self, node_id: str, status: NodeStatus) -> None:
        node = self.nodes[node_id]
        allowed = {
            NodeStatus.PENDING: {NodeStatus.EXPANDING, NodeStatus.FAILED},
            NodeStatus.EXPANDING: {NodeStatus.EVALUATING, NodeStatus.FAILED},
            NodeStatus.EVALUATING: {NodeStatus.EVALUATED, NodeStatus.FAILED},
            NodeStatus.EVALUATED: {NodeStatus.EXPANDING, NodeStatus.PRUNED},
            NodeStatus.FAILED: {NodeStatus.PRUNED},
            NodeStatus.PRUNED: set(),
        }
        if status not in allowed[node.status]:
            raise ValueError("invalid lifecycle transition")
        node.status = status
        node.updated_at = now()


class HistoryEntry(Frozen):
    candidate: Candidate
    evaluation: EvaluationResult | None


class BranchTask(Frozen):
    task_id: str
    parent_node_id: str
    problem: VisibleProblem
    history: tuple[HistoryEntry, ...]
    strategy_hint: str | None = None
    max_candidates: int = Field(ge=1)
    max_llm_calls: int = Field(ge=1)
    max_wall_time_seconds: float = Field(gt=0)


class CandidateResult(Frozen):
    candidate: Candidate
    evaluation: EvaluationResult | None
    refinement_step: int
    generation_metadata: dict[str, Any] = Field(default_factory=dict)


class BranchResult(BaseModel):
    task_id: str
    parent_node_id: str
    candidates: list[CandidateResult] = Field(default_factory=list)
    status: str = "COMPLETED"
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_seconds: float = 0
    error: str | None = None
