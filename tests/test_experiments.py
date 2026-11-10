import json

import pytest

from branchforge.experiments.dataset import Problem, parse_public, select
from branchforge.experiments.report import aggregate, generate, wilson
from branchforge.experiments.runner import ExperimentConfig, preflight
from branchforge.models import TestCase


def problem(i=0):
    return Problem(
        question_id=str(i),
        title="Sum",
        statement="Sum inputs",
        platform="atcoder",
        difficulty="easy" if i % 2 else "hard",
        contest_date="2025-01-01",
        public_tests=(TestCase(input="1 2", expected_output="3"),),
    )


def row(problem_id="0", variant="baseline", passed=True, trial=0):
    return {
        "problem_id": problem_id,
        "variant": variant,
        "trial": trial,
        "run_id": "abc",
        "grade": {"passed": passed, "status": "PASS" if passed else "FAIL"},
        "visible_reward": 1,
        "first_visible_reward": 0,
        "budget": {
            "llm_calls": 2,
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
            "candidates": 2,
            "evaluations": 2,
            "elapsed_seconds": 1,
            "cost_usd": None,
        },
    }


def test_selection_stable_and_stratified():
    population = [problem(i) for i in range(20)]
    chosen = select(population, 10, 42)
    assert chosen == select(list(reversed(population)), 10, 42)
    assert len({p.question_id for p in chosen}) == 10
    assert {p.difficulty for p in chosen} == {"easy", "hard"}
    with pytest.raises(ValueError):
        select(population, 21, 42)


def test_private_payload_never_parsed_or_exposed():
    raw = {
        "question_id": "x",
        "question_title": "x",
        "question_content": "x",
        "platform": "leetcode",
        "difficulty": "easy",
        "contest_date": "2025-01-01",
        "starter_code": "class Solution: pass",
        "metadata": '{"func_name": "sum"}',
        "private_test_cases": "SECRET INVALID PICKLE",
        "public_test_cases": json.dumps(
            [{"input": "[1,2]", "output": "3", "testtype": "functional"}]
        ),
    }
    parsed = parse_public(raw)
    assert parsed.function_name == "sum"
    assert "SECRET" not in parsed.visible().model_dump_json()
    assert "Solution.sum" in parsed.visible().input_format


def test_statistics_missing_cost_zero_solves_and_recovery():
    result = aggregate([row(passed=False), row("1", passed=None)])
    m = result["metrics"]["baseline"]
    assert m["solve_rate"] == 0
    assert m["unknown_grades"] == 1
    assert m["cost_per_solved"] is None
    assert m["recovery_opportunities"] == 2
    assert m["recovery_rate"] == 0
    assert wilson(0, 0) is None
    assert wilson(5, 10)[0] == pytest.approx(0.23659, abs=0.00001)


def test_paired_clusters_keep_trials_together():
    rows = [
        row(str(i), variant, bool(i), trial)
        for i in range(2)
        for trial in range(3)
        for variant in ("baseline", "mcts")
    ]
    comparison = aggregate(rows)["paired"][0]
    assert comparison["paired_problems"] == 2
    assert comparison["paired_trials"] == 6
    assert comparison["ci95"] == [0, 0]


def test_report_fixture_and_escaping(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "stage": "validation",
                "fixture": True,
                "expected_trials": 1,
                "title": '<script>alert("x & y > z")</script>',
            }
        )
    )
    (tmp_path / "trials.json").write_text(json.dumps([row()]))
    generate(tmp_path)
    assert "DETERMINISTIC FIXTURE" in (tmp_path / "report.md").read_text()
    assert "<script>" not in (tmp_path / "report.html").read_text()
    from html.parser import HTMLParser

    class CodeText(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.inside = False
            self.text = ""

        def handle_starttag(self, tag, attrs):
            if tag == "code":
                self.inside = True

        def handle_endtag(self, tag):
            if tag == "code":
                self.inside = False

        def handle_data(self, data):
            if self.inside:
                self.text += data

    parser = CodeText()
    parser.feed((tmp_path / "report.html").read_text())
    manifest_text = json.dumps(json.loads((tmp_path / "manifest.json").read_text()), indent=2)
    assert manifest_text in parser.text
    assert "&quot;" not in parser.text
    assert "&lt;script&gt;" not in parser.text

    assert (tmp_path / "results.csv").exists()
    assert (tmp_path / "solve-rates.svg").exists()


def test_preflight_counts_all_variants():
    c = ExperimentConfig()
    c.search.budget.max_llm_calls = 8
    estimate = preflight(c, 100)
    assert estimate["trials"] == 600
    assert estimate["physical_request_ceiling"] == 4100


@pytest.mark.docker
async def test_official_grader_both_conventions_and_private_isolation(tmp_path):
    from branchforge.config import ExecutionConfig
    from branchforge.execution import DockerExecutor
    from branchforge.experiments.grading import OfficialGrader

    executor = DockerExecutor(ExecutionConfig(image="branchforge-lcb:28fef95"))
    try:
        await executor.check()
    except (RuntimeError, FileNotFoundError):
        pytest.skip("Pinned LiveCodeBench image or Docker unavailable")
    grader = OfficialGrader(executor)
    p = problem().visible()
    assert (await grader.grade("print(sum(map(int,input().split())))", p, None)).passed is True
    assert (await grader.grade("print(99)", p, None)).passed is False
    functional = p.model_copy(
        update={"visible_tests": (TestCase(input="[1,2]", expected_output="3"),)}
    )
    code = "class Solution:\n    def total(self, values): return sum(values)"
    assert (await grader.grade(code, functional, "total")).passed is True
    private = json.dumps([{"input": "SECRET", "output": "2", "testtype": "stdin"}])
    grade = await grader.grade("print(3)", p, None, private)
    assert grade.passed is False
    assert grade.flags == []
    assert "SECRET" not in grade.model_dump_json()


@pytest.mark.docker
async def test_fixture_full_pipeline_all_variants(tmp_path):
    from fastapi.testclient import TestClient

    from branchforge.api.app import create_app
    from branchforge.config import Config, ExecutionConfig
    from branchforge.execution import DockerExecutor
    from branchforge.experiments.grading import OfficialGrader, PublicEvaluator
    from branchforge.experiments.runner import VARIANTS, save
    from branchforge.llm import FakeLLM
    from branchforge.search import SearchOrchestrator

    executor = DockerExecutor(ExecutionConfig(image="branchforge-lcb:28fef95"))
    try:
        await executor.check()
    except (RuntimeError, FileNotFoundError):
        pytest.skip("Pinned LiveCodeBench image or Docker unavailable")
    grader = OfficialGrader(executor)
    p = problem().visible()
    rows = []
    directory = tmp_path / "experiment-fixture"
    directory.mkdir()
    for variant in VARIANTS:
        config = Config(runs_dir=tmp_path)
        config.budget.max_llm_calls = config.budget.max_candidates = 2
        config.budget.max_tokens = None
        config.agents.max_concurrent = 1 if variant == "beam-sequential" else 2
        config.llm.retries = 0
        algorithm = (
            "beam"
            if variant.startswith("beam-")
            else "baseline"
            if variant == "single-shot"
            else variant
        )
        search = SearchOrchestrator(
            p,
            config,
            algorithm,
            client=FakeLLM({"default": ["print(sum(map(int,input().split())))"]}),
            evaluator=PublicEvaluator(grader, None),
        )
        result = await search.run()
        assert result["candidate"] is not None
        grade = await grader.grade(
            result["candidate"]["code"],
            p,
            None,
            json.dumps([{"input": "2 3", "output": "5", "testtype": "stdin"}]),
        )
        assert grade.passed is True
        rows.append(
            dict(
                **result,
                problem_id=p.problem_id,
                variant=variant,
                trial=0,
                first_visible_reward=1,
                grade=grade.model_dump(),
            )
        )
    save(
        directory / "manifest.json", {"stage": "validation", "fixture": True, "expected_trials": 6}
    )
    save(directory / "trials.json", rows)
    generate(directory)
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/experiments").json()["data"][0]["experiment_id"] == "experiment-fixture"
    detail = client.get("/api/experiments/experiment-fixture").json()["data"]
    assert len(detail["trials"]) == 6
    assert client.get(f"/api/runs/{rows[0]['run_id']}/tree").status_code == 200


async def test_runner_freeze_resume_and_paid_guard(tmp_path, monkeypatch):
    from branchforge.experiments import runner
    from branchforge.experiments.dataset import DATASET_REVISION, GRADER_REVISION, RELEASE
    from branchforge.experiments.grading import Grade
    from branchforge.models import SearchTree
    from branchforge.runtime import Events

    config = ExperimentConfig(spending_limit_usd=1000)
    config.search.llm.provider = "litellm"
    config.search.budget.max_tokens = None
    config.search.runs_dir = tmp_path / "runs"
    config.search.budget.max_llm_calls = 8
    manifest = tmp_path / "selection.json"
    runner.save(
        manifest,
        {
            "dataset_revision": DATASET_REVISION,
            "release": RELEASE,
            "problems": [problem(i).model_dump(mode="json") for i in range(20)],
            "file_hashes": {},
        },
    )
    output = config.search.runs_dir / "experiment-test"
    with pytest.raises(ValueError, match="allow-paid"):
        await runner.run(config, manifest, tmp_path, output)

    calls = []

    class Executor:
        def __init__(self, config):
            pass

        async def check(self):
            pass

        async def command(self, *args):
            return 0, GRADER_REVISION, ""

    class Search:
        def __init__(self, p, settings, algorithm, evaluator):
            self.run_id = str(len(calls))
            calls.append((p.problem_id, algorithm, settings.agents.max_concurrent))
            self.events = Events(settings.runs_dir / self.run_id, self.run_id)

        async def run(self):
            self.events.save("tree.json", SearchTree().model_dump(mode="json"))
            result = row()
            result.update(run_id=self.run_id, candidate={"code": "print(3)"})
            for key in ("problem_id", "variant", "trial", "grade", "first_visible_reward"):
                result.pop(key)
            return result

    class Grader:
        def __init__(self, executor):
            self.executor = executor

        async def grade(self, code, p, function, private):
            assert list(output.glob("*.selected.json"))
            return Grade(passed=True, status="PASS")

    monkeypatch.setattr(runner, "DockerExecutor", Executor)
    monkeypatch.setattr(runner, "SearchOrchestrator", Search)
    monkeypatch.setattr(runner, "OfficialGrader", Grader)
    monkeypatch.setattr(runner, "private_row", lambda *a: {"private_test_cases": "[]"})
    monkeypatch.setattr(runner, "generate", lambda path: {})
    monkeypatch.setattr(runner, "aggregate", lambda rows: {})
    await runner.run(config, manifest, tmp_path, output, True)
    assert len(calls) == 120
    assert len(json.loads((output / "trials.json").read_text())) == 120
    await runner.run(config, manifest, tmp_path, output, True)
    assert len(calls) == 120
    config.seed += 1
    with pytest.raises(ValueError, match="frozen manifest"):
        await runner.run(config, manifest, tmp_path, output, True)


def test_smoke_ceiling_fits_authorized_cap():
    from pathlib import Path

    import yaml

    config = ExperimentConfig.model_validate(
        yaml.safe_load(Path("configs/livecodebench-smoke.yaml").read_text())
    )
    assert config.stage == "smoke"
    assert config.spending_limit_usd == 5
    estimate = preflight(config, 2)
    assert estimate["trials"] == 12
    assert estimate["physical_request_ceiling"] == 22
    assert estimate["conservative_cost_ceiling_usd"] < 5


def test_followup_has_explicit_unique_ids():
    with pytest.raises(ValueError, match="distinct explicit"):
        ExperimentConfig(stage="followup")
    with pytest.raises(ValueError, match="distinct explicit"):
        ExperimentConfig(stage="followup", followup_problem_ids=("a", "a"))
    config = ExperimentConfig(
        stage="followup",
        followup_problem_ids=("a", "b"),
        variants=("baseline",),
        grader_memory_limit_mb=1024,
    )
    assert preflight(config, 2)["trials"] == 2


async def test_grader_memory_override_is_confined_to_sandbox():
    from branchforge.experiments.grading import OfficialGrader

    class Executor:
        async def run(self, code, stdin, sandbox):
            assert sandbox.memory_limit_mb == 1024
            return 'BRANCHFORGE_GRADE={"passed":false,"flags":[],"error_code":-2}', "", 0, None

    p = problem().visible()
    grade = await OfficialGrader(Executor(), memory_limit_mb=1024).grade("print(0)", p, None)
    assert grade.passed is False
    assert p.memory_limit_mb == 512


def test_condensed_primary_protocol():
    from pathlib import Path

    import yaml

    config = ExperimentConfig.model_validate(
        yaml.safe_load(Path("configs/livecodebench-primary.yaml").read_text())
    )
    assert config.stage == "primary"
    assert config.problem_count == 50
    assert len(config.variants) == 5
    assert preflight(config, config.problem_count)["trials"] == 250
    assert config.spending_limit_usd is None


def test_funding_amendment_preserves_research_protocol():
    import copy

    from branchforge.experiments.runner import fingerprint, validate_funding_amendment

    original = {
        "config": ExperimentConfig().model_dump(mode="json"),
        "source_hash": "old",
        "estimate": {"trials": 250, "spending_limit_usd": 12.86, "spending_mode": "per_request"},
        "problem_ids": ["a"],
        "selection_hash": "fixed",
    }
    current = copy.deepcopy(original)
    current["config"].update(spending_mode="unlimited", spending_limit_usd=None)
    current["estimate"].update(spending_mode="unlimited", spending_limit_usd=None)
    current["source_hash"] = "new"
    auth = {
        "original_manifest_hash": fingerprint(original),
        "authorized_config_hash": fingerprint(current["config"]),
        "authorized_source_hash": "new",
    }
    validate_funding_amendment(original, current, auth)
    current["config"]["search"]["llm"]["max_output_tokens"] = 50000
    auth["authorized_config_hash"] = fingerprint(current["config"])
    with pytest.raises(ValueError, match="research settings"):
        validate_funding_amendment(original, current, auth)
