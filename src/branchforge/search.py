import asyncio
import math
import time
from typing import Any, Protocol

from .agents import BranchWorkerPool, CodingAgent
from .config import Config
from .execution import DockerExecutor, Evaluator
from .llm import FakeLLM, LiteLLMClient, LLMClient
from .models import (
    BranchTask,
    HistoryEntry,
    NodeStatus,
    SearchNode,
    SearchTree,
    VisibleProblem,
    uid,
)
from .runtime import Budget, Events


def ranked(nodes: list[SearchNode]) -> list[SearchNode]:
    return sorted(
        [n for n in nodes if n.evaluation and n.evaluation.reward is not None],
        key=lambda n: (-float(n.evaluation.reward), n.order),  # type: ignore[union-attr,arg-type]
    )  # type: ignore[union-attr,arg-type]


class SearchPolicy(Protocol):
    async def search(self, context: "SearchOrchestrator") -> str: ...


class Baseline:
    async def search(self, context: "SearchOrchestrator") -> str:
        parent = "root"
        for _ in range(context.config.budget.max_candidates):
            nodes = await context.expand([parent], 1, 1, context.config.budget.max_candidates)
            valid = ranked(nodes)
            if not valid:
                return context.budget.reason or "ERROR"
            if valid[0].evaluation.reward == 1:  # type: ignore[union-attr]
                return "SUCCESS"
            parent = nodes[-1].node_id
        return context.budget.reason or "MAX_CANDIDATES"


class BestOfN:
    async def search(self, context: "SearchOrchestrator") -> str:
        nodes = await context.expand(["root"], context.config.best_of_n, 1, 1)
        best = ranked(nodes)
        if best and best[0].evaluation.reward == 1:  # type: ignore[union-attr]
            return "SUCCESS"
        return context.budget.reason or "SEARCH_EXHAUSTED"


class Beam:
    async def search(self, context: "SearchOrchestrator") -> str:
        cfg = context.config.beam_search
        frontier = ["root"]
        for iteration in range(cfg.max_frontier_iterations):
            context.events.emit("NODE_SELECTED", frontier_index=iteration, node_ids=frontier)
            nodes = await context.expand(
                frontier,
                cfg.branching_factor,
                min(
                    context.config.agents.max_candidates_per_task,
                    context.config.agents.max_refinement_steps + 1,
                ),
                cfg.max_depth,
            )
            candidates = ranked(nodes)
            keep = candidates[: cfg.beam_width]
            survivors = {n.node_id for n in keep}
            for node in nodes:
                if node.node_id not in survivors:
                    context.tree.transition(node.node_id, NodeStatus.PRUNED)
                    context.events.emit(
                        "NODE_PRUNED", node_id=node.node_id, frontier_index=iteration
                    )
            context.events.emit(
                "FRONTIER_PRUNED", frontier_index=iteration, survivors=list(survivors)
            )
            context.snapshot()
            if keep and keep[0].evaluation.reward == 1:  # type: ignore[union-attr]
                return "SUCCESS"
            frontier = [n.node_id for n in keep if n.depth < cfg.max_depth]
            if not candidates and nodes:
                return "ERROR"
            if not frontier or context.budget.reason:
                return context.budget.reason or "SEARCH_EXHAUSTED"
        return "SEARCH_EXHAUSTED"


def uct(node: SearchNode, parent_visits: int, constant: float) -> float:
    if not node.visits:
        return math.inf
    return node.total_reward / node.visits + constant * math.sqrt(
        math.log(max(1, parent_visits)) / node.visits
    )


class MCTS:
    async def search(self, context: "SearchOrchestrator") -> str:
        cfg = context.config.mcts

        def expandable(node: SearchNode) -> bool:
            if node.depth >= cfg.max_depth:
                return False
            if len(node.children_ids) < cfg.branching_factor:
                return True
            return any(expandable(context.tree.nodes[c]) for c in node.children_ids)

        for simulation in range(cfg.max_simulations):
            node = context.tree.nodes["root"]
            if not expandable(node):
                return "SEARCH_EXHAUSTED"
            while len(node.children_ids) >= cfg.branching_factor:
                children = [
                    context.tree.nodes[c]
                    for c in node.children_ids
                    if expandable(context.tree.nodes[c])
                ]
                node = max(
                    children,
                    key=lambda n: (uct(n, node.visits, cfg.exploration_constant), -n.order),
                )
            context.events.emit("NODE_SELECTED", node_id=node.node_id, simulation=simulation)
            created = await context.expand([node.node_id], 1, 1, cfg.max_depth)
            valid = ranked(created)
            if not valid:
                return context.budget.reason or "ERROR"
            leaf = valid[0]
            reward = float(leaf.evaluation.reward)  # type: ignore[union-attr,arg-type]
            for ancestor in context.tree.path(leaf.node_id):
                ancestor.visits += 1
                ancestor.total_reward += reward
            context.events.emit(
                "REWARD_BACKPROPAGATED", node_id=leaf.node_id, simulation=simulation, reward=reward
            )
            context.snapshot()
            if reward == 1:
                return "SUCCESS"
        return "SEARCH_EXHAUSTED"


POLICIES: dict[str, type] = {"baseline": Baseline, "best-of-n": BestOfN, "beam": Beam, "mcts": MCTS}


class SearchOrchestrator:
    def __init__(
        self,
        problem: VisibleProblem,
        config: Config,
        algorithm: str,
        client: LLMClient | None = None,
        evaluator: Evaluator | None = None,
    ):
        if algorithm not in POLICIES:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        if type(problem) is not VisibleProblem:
            raise ValueError("Search accepts only a redacted VisibleProblem")
        self.problem, self.config, self.algorithm = problem, config, algorithm
        self.run_id = uid()
        self.events = Events(config.runs_dir / self.run_id, self.run_id)
        self.tree = SearchTree()
        self.budget = Budget(config, self.events)
        self.evaluator = evaluator or Evaluator(DockerExecutor(config.execution))
        self.agent = CodingAgent(
            config,
            client or (FakeLLM() if config.llm.provider == "fake" else LiteLLMClient()),
            self.evaluator,
            self.budget,
            self.events,
        )
        concurrency = 1 if algorithm in {"baseline", "mcts"} else config.agents.max_concurrent
        self.pool = BranchWorkerPool(concurrency, self.agent, self.events)
        self.task_index = 0
        self.frontier_index = 0
        self.frontier_durations: list[float] = []
        self.error: str | None = None

    def snapshot(self) -> None:
        self.events.save("tree.json", self.tree.model_dump(mode="json"))

    async def expand(
        self, parents: list[str], branching: int, chain: int, max_depth: int
    ) -> list[SearchNode]:
        tasks = []
        started = time.monotonic()
        for parent_id in parents:
            parent = self.tree.nodes[parent_id]
            for alternative in range(branching):
                count = min(chain, max_depth - parent.depth)
                if count <= 0:
                    continue
                task_id = f"task-{self.task_index:06d}"
                self.task_index += 1
                reservation = self.budget.reserve(
                    task_id,
                    count,
                    min(self.config.agents.max_llm_calls, count * (self.config.llm.retries + 1)),
                )
                if reservation is None:
                    self.events.emit(
                        "BRANCH_TASK_SKIPPED", task_id=task_id, reason=self.budget.reason
                    )
                    break
                candidates, calls = reservation
                history = tuple(
                    HistoryEntry(candidate=n.candidate, evaluation=n.evaluation)
                    for n in self.tree.path(parent_id)
                    if n.candidate
                )
                hints = ("Greedy", "Dynamic programming", "Alternative approach")
                task = BranchTask(
                    task_id=task_id,
                    parent_node_id=parent_id,
                    problem=self.problem,
                    history=history,
                    strategy_hint=hints[alternative % len(hints)],
                    max_candidates=candidates,
                    max_llm_calls=calls,
                    max_wall_time_seconds=self.config.agents.max_wall_time_seconds,
                )
                tasks.append(task)
                self.events.emit("BRANCH_TASK_CREATED", task_id=task_id, node_id=parent_id)
                self.events.emit("NODE_EXPANSION_STARTED", node_id=parent_id, task_id=task_id)
        created = []
        try:
            await self.pool.run(tasks)
        finally:
            # Results survive cancellation and are always committed in assignment order.
            for task in tasks:
                result = self.agent.results.get(task.task_id)
                try:
                    if result is not None:
                        if (
                            result.task_id != task.task_id
                            or result.parent_node_id != task.parent_node_id
                        ):
                            raise ValueError("Task identity mismatch")
                        commit_parent = task.parent_node_id
                        for record in result.candidates:
                            node = self.tree.add(
                                commit_parent,
                                record.candidate,
                                record.evaluation,
                                max_depth,
                                task.task_id,
                            )
                            created.append(node)
                            commit_parent = node.node_id
                            self.events.emit(
                                "NODE_CREATED",
                                node_id=node.node_id,
                                task_id=task.task_id,
                                order=node.order,
                            )
                finally:
                    self.budget.release(task)
            duration = time.monotonic() - started
            self.frontier_durations.append(duration)
            self.events.emit(
                "FRONTIER_COMPLETED", frontier_index=self.frontier_index, duration_seconds=duration
            )
            self.frontier_index += 1
            self.snapshot()
        return created

    async def run(self) -> dict[str, Any]:
        self.events.save("config.json", self.config.model_dump(mode="json"))
        self.events.save("problem.json", self.problem.model_dump(mode="json"))
        self.events.emit("RUN_STARTED", algorithm=self.algorithm)
        reason = "ERROR"
        try:
            async with asyncio.timeout(self.config.budget.max_wall_time_seconds):
                if isinstance(self.evaluator.executor, DockerExecutor):
                    await self.evaluator.executor.check()
                reason = await POLICIES[self.algorithm]().search(self)
        except TimeoutError:
            reason = "MAX_WALL_TIME"
        except asyncio.CancelledError:
            reason = "USER_CANCELED"
        except Exception as exc:  # noqa: BLE001 -- persist failed runs before returning
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            best = ranked(list(self.tree.nodes.values()))
            final = best[0] if best else None
            elapsed = time.monotonic() - self.budget.started
            docker = self.evaluator.executor
            results = list(self.agent.results.values())
            result = {
                "run_id": self.run_id,
                "algorithm": self.algorithm,
                "termination_reason": reason,
                "error": self.error,
                "selected_node_id": final.node_id if final else None,
                "candidate": final.candidate.model_dump(mode="json")
                if final and final.candidate
                else None,
                "visible_reward": final.evaluation.reward if final and final.evaluation else None,
                "budget": self.budget.summary(),
                "concurrency": {
                    "max_subagents": self.pool.slots.maximum,
                    "max_llm_requests": self.agent.llm_slots.maximum,
                    "max_containers": docker.limiter.maximum
                    if isinstance(docker, DockerExecutor)
                    else None,
                    "average_active_subagents": self.pool.active_seconds / max(elapsed, 1e-9),
                    "queue_wait_seconds": self.pool.queue_waits,
                    "worker_execution_seconds": [r.elapsed_seconds for r in results],
                    "frontier_seconds": self.frontier_durations,
                    "failed_tasks": sum(r.status == "FAILED" for r in results),
                    "canceled_tasks": sum(r.status == "CANCELED" for r in results),
                },
                "average_depth": sum(n.depth for n in self.tree.nodes.values())
                / len(self.tree.nodes),
            }
            self.events.emit("RUN_FINISHED", termination_reason=reason, error=self.error)
            self.snapshot()
            self.events.save("result.json", result)
        return result
