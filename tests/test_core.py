import asyncio
import json

import pytest
from typer.testing import CliRunner

from branchforge.cli import app
from branchforge.config import Config
from branchforge.execution import DockerExecutor, Evaluator, normalize
from branchforge.llm import FakeLLM, GenerationResult
from branchforge.models import (
    Candidate,
    CodingProblem,
    NodeStatus,
    SearchTree,
    TestCase,
    VisibleProblem,
)
from branchforge.search import SearchOrchestrator, uct


@pytest.fixture
def problem():
    return VisibleProblem(
        problem_id="test",
        title="Test",
        statement="Return input",
        input_format="int",
        output_format="int",
        visible_tests=(
            TestCase(input="1", expected_output="1"),
            TestCase(input="2", expected_output="2"),
        ),
    )


class ScriptExecutor:
    """Test double: recognizes fixture labels; never executes generated code."""

    async def run(self, code, stdin, problem):
        await asyncio.sleep(0)
        return (
            stdin if code == "good" or (code == "partial" and stdin == "1") else "bad",
            "",
            0,
            None,
        )


def settings(tmp_path):
    cfg = Config(runs_dir=tmp_path / "runs")
    cfg.budget.max_tokens = None
    return cfg


async def test_parallel_frontier_isolation_and_inspection(problem, tmp_path):
    class BarrierFake(FakeLLM):
        def __init__(self):
            super().__init__(
                {
                    "Greedy": ["bad", "bad"],
                    "Dynamic programming": ["partial", "good"],
                    "Alternative approach": ["bad"],
                }
            )
            self.started = 0
            self.barrier = asyncio.Event()

        async def generate(self, messages, config):
            if "Ancestor" not in messages[0]["content"]:
                self.started += 1
                if self.started == 3:
                    self.barrier.set()
                await self.barrier.wait()
            return await super().generate(messages, config)

    fake = BarrierFake()
    search = SearchOrchestrator(
        problem, settings(tmp_path), "beam", fake, Evaluator(ScriptExecutor())
    )
    async with asyncio.timeout(5):
        result = await search.run()
    assert result["termination_reason"] == "SUCCESS"
    assert result["concurrency"]["max_subagents"] == 3
    assert result["budget"]["llm_calls"] == 8
    assert len(search.tree.nodes) == 9
    assert not search.budget.quotas
    assert search.pool.slots.active == 0
    assert search.agent.llm_slots.active == 0
    for conversation in fake.seen:
        prompt = conversation[0]["content"]
        hint = prompt.split("Optional strategy: ")[1].split("\n")[0]
        if hint == "Greedy":
            assert '"code":"good"' not in prompt
    artifact = search.events.directory
    restored = SearchTree.model_validate_json((artifact / "tree.json").read_text())
    assert restored == search.tree
    events = [json.loads(line) for line in (artifact / "events.jsonl").read_text().splitlines()]
    commits = [event["task_id"] for event in events if event["event_type"] == "NODE_CREATED"]
    assert commits == sorted(commits)
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    output = CliRunner().invoke(app, ["inspect", search.run_id, "--runs-dir", str(artifact.parent)])
    assert output.exit_code == 0, output.output
    assert "SELECTED" in output.output


@pytest.mark.parametrize("algorithm", ["baseline", "best-of-n", "beam", "mcts"])
async def test_algorithms_and_budget(problem, tmp_path, algorithm):
    cfg = settings(tmp_path)
    cfg.budget.max_candidates = 4
    cfg.budget.max_llm_calls = 5
    fake = FakeLLM({"default": ["bad"]})
    search = SearchOrchestrator(problem, cfg, algorithm, fake, Evaluator(ScriptExecutor()))
    result = await search.run()
    assert result["termination_reason"] in {"MAX_CANDIDATES", "MAX_LLM_CALLS", "SEARCH_EXHAUSTED"}
    assert result["budget"]["candidates"] <= 4
    assert result["budget"]["llm_calls"] <= 5
    assert search.tree.integrity()
    if algorithm == "mcts":
        assert search.tree.nodes["root"].visits == result["budget"]["evaluations"]


async def test_sequential_parallel_equivalence(problem, tmp_path):
    outputs = []
    for concurrency in [1, 3]:
        cfg = settings(tmp_path / str(concurrency))
        cfg.agents.max_concurrent = concurrency
        cfg.beam_search.max_depth = 2
        fake = FakeLLM({"default": ["bad"]})
        search = SearchOrchestrator(problem, cfg, "beam", fake, Evaluator(ScriptExecutor()))
        result = await search.run()
        outputs.append(
            (
                [(n.node_id, n.parent_id, n.status) for n in search.tree.nodes.values()],
                result["selected_node_id"],
                result["budget"]["llm_calls"],
            )
        )
    assert outputs[0] == outputs[1]


async def test_cancellation_preserves_and_releases(problem, tmp_path):
    entered = asyncio.Event()

    class BlockingExecutor(ScriptExecutor):
        async def run(self, code, stdin, problem):
            entered.set()
            await asyncio.Event().wait()

    search = SearchOrchestrator(
        problem,
        settings(tmp_path),
        "beam",
        FakeLLM({"default": ["bad"]}),
        Evaluator(BlockingExecutor()),
    )
    task = asyncio.create_task(search.run())
    await entered.wait()
    task.cancel()
    result = await task
    assert result["termination_reason"] == "USER_CANCELED"
    assert len(search.tree.nodes) > 1
    assert search.pool.slots.active == search.agent.llm_slots.active == 0
    assert not search.budget.quotas


async def test_malformed_and_failed_workers(problem, tmp_path):
    class Malformed(FakeLLM):
        async def generate(self, messages, config):
            return GenerationResult(content="not JSON", input_tokens=3, output_tokens=2)

    search = SearchOrchestrator(
        problem, settings(tmp_path), "beam", Malformed(), Evaluator(ScriptExecutor())
    )
    result = await search.run()
    assert result["candidate"] is None
    assert result["budget"]["llm_calls"] == 9
    assert result["budget"]["total_tokens"] == 45
    assert result["concurrency"]["failed_tasks"] == 3


async def test_dedup_and_infrastructure(problem):
    evaluator = Evaluator(ScriptExecutor())
    one = Candidate(explanation="", code="good")
    two = Candidate(explanation="", code="good")
    a, b = await asyncio.gather(evaluator.evaluate(one, problem), evaluator.evaluate(two, problem))
    assert a.reward == b.reward == 1
    assert a.candidate_id != b.candidate_id
    assert evaluator.executions == 2

    class Broken(ScriptExecutor):
        async def run(self, *args):
            return "", "daemon failed", None, "INFRASTRUCTURE_ERROR"

    evaluator = Evaluator(Broken())
    assert (await evaluator.evaluate(one, problem)).reward is None
    assert not evaluator.cache


def test_tree_and_normalization():
    tree = SearchTree()
    candidate = Candidate(explanation="", code="")
    node = tree.add("root", candidate, None, 2)
    assert tree.path(node.node_id)[0].node_id == "root"
    assert tree.leaves() == [node]
    with pytest.raises(ValueError):
        tree.add("root", candidate, None, 2)
    with pytest.raises(ValueError):
        tree.transition(node.node_id, NodeStatus.EVALUATED)
    assert uct(node, 0, 1.414) == float("inf")
    assert normalize("a  \r\nb\n") == "a\nb"
    assert normalize("a b") != normalize("a  b")


def test_hidden_boundary(problem, tmp_path):
    full = CodingProblem(
        **problem.model_dump(), hidden_tests=[TestCase(input="SECRET", expected_output="HIDDEN")]
    )
    assert "SECRET" not in full.visible().model_dump_json()
    with pytest.raises(ValueError):
        SearchOrchestrator(full, settings(tmp_path), "beam")


async def test_docker_unavailable_fails_closed(problem, tmp_path, monkeypatch):
    async def unavailable(self):
        raise RuntimeError("Docker unavailable")

    monkeypatch.setattr(DockerExecutor, "check", unavailable)
    search = SearchOrchestrator(problem, settings(tmp_path), "beam")
    result = await search.run()
    assert result["termination_reason"] == "ERROR"
    assert result["budget"]["llm_calls"] == 0
    assert (search.events.directory / "tree.json").exists()


async def test_deadline(problem, tmp_path):
    class Slow(FakeLLM):
        async def generate(self, messages, config):
            await asyncio.Event().wait()

    cfg = settings(tmp_path)
    cfg.budget.max_wall_time_seconds = 0.05
    search = SearchOrchestrator(problem, cfg, "beam", Slow(), Evaluator(ScriptExecutor()))
    result = await search.run()
    assert result["termination_reason"] == "MAX_WALL_TIME"
    assert not search.budget.quotas
    assert search.agent.llm_slots.active == 0


async def test_atomic_admission_and_token_ceiling(problem, tmp_path):
    cfg = settings(tmp_path)
    cfg.budget.max_tokens = cfg.llm.max_prompt_chars + cfg.llm.max_output_tokens
    search = SearchOrchestrator(
        problem, cfg, "beam", FakeLLM({"default": ["bad"]}), Evaluator(ScriptExecutor())
    )
    result = await search.run()
    assert result["budget"]["llm_calls"] == 1
    assert result["budget"]["total_tokens"] <= cfg.budget.max_tokens
    assert result["termination_reason"] == "MAX_TOKENS"
    assert (
        search.budget.reserved_calls
        == search.budget.reserved_candidates
        == search.budget.reserved_tokens
        == 0
    )


async def test_worker_failure_does_not_lose_other_results(problem, tmp_path):
    cfg = settings(tmp_path)
    fake = FakeLLM(
        {
            "Greedy": [RuntimeError("failure")],
            "Dynamic programming": ["good"],
            "Alternative approach": ["bad"],
        }
    )
    search = SearchOrchestrator(problem, cfg, "beam", fake, Evaluator(ScriptExecutor()))
    result = await search.run()
    assert result["termination_reason"] == "SUCCESS"
    assert result["concurrency"]["failed_tasks"] == 1
    assert search.tree.integrity()


def test_invalid_config_and_cycles():
    with pytest.raises(ValueError):
        Config.model_validate({"agents": {"max_concurrent": 0}})
    tree = SearchTree()
    node = tree.add("root", Candidate(explanation="", code=""), None, 1)
    node.children_ids.append("root")
    with pytest.raises(ValueError):
        SearchTree.model_validate_json(tree.model_dump_json())


@pytest.mark.parametrize("algorithm", ["baseline", "best-of-n", "beam", "mcts"])
async def test_dashboard_trace_contract(problem, tmp_path, algorithm):
    cfg = settings(tmp_path)
    cfg.budget.max_candidates = 8
    runner = SearchOrchestrator(
        problem, cfg, algorithm, FakeLLM({"default": ["bad"]}), Evaluator(ScriptExecutor())
    )
    result = await runner.run()
    events = [
        json.loads(line)
        for line in (runner.events.directory / "events.jsonl").read_text().splitlines()
    ]
    assert all(e["schema_version"] == 2 for e in events)
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["root"]["node_id"] == "root"
    assert (
        next(e for e in events if e["event_type"] == "FINAL_SELECTED")["node_id"]
        == result["selected_node_id"]
    )
    for created in (e for e in events if e["event_type"] == "NODE_CREATED"):
        generated = next(
            e
            for e in events
            if e["event_type"] == "CANDIDATE_GENERATED" and e["candidate_id"] == created["node_id"]
        )
        assert generated["sequence"] < created["sequence"]
        assert generated["candidate"] == created["node"]["candidate"]
    assert all(
        e["worker_id"].startswith("worker-")
        for e in events
        if e["event_type"] == "SUBAGENT_STARTED"
    )
