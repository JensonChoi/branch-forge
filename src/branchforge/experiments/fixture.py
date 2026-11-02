"""Credential-free demonstration using the actual Docker checker and scripted candidates."""

from pathlib import Path
from typing import Any

from ..config import Config, ExecutionConfig
from ..execution import DockerExecutor
from ..llm import FakeLLM
from ..models import TestCase, VisibleProblem
from ..search import SearchOrchestrator
from .grading import OfficialGrader, PublicEvaluator
from .report import generate
from .runner import VARIANTS, save


async def fixture(output: Path, runs_dir: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError("Fixture output already exists; choose a new directory")
    executor = DockerExecutor(ExecutionConfig(image="branchforge-lcb:28fef95"))
    await executor.check()
    output.mkdir(parents=True)
    grader = OfficialGrader(executor)
    problem = VisibleProblem(
        problem_id="fixture-sum",
        title="FIXTURE: sum two integers",
        statement="Print the sum of two integers.",
        input_format="stdin",
        output_format="stdout",
        visible_tests=(TestCase(input="1 2", expected_output="3"),),
        memory_limit_mb=512,
    )
    rows = []
    save(
        output / "manifest.json",
        {
            "stage": "validation",
            "fixture": True,
            "expected_trials": 6,
            "problem_ids": [problem.problem_id],
            "config": {"provider": "fake"},
            "note": "Scripted fixture validates plumbing; it is not benchmark evidence.",
        },
    )
    for variant in VARIANTS:
        config = Config(runs_dir=runs_dir)
        config.budget.max_llm_calls = config.budget.max_candidates = 2
        config.budget.max_tokens = None
        config.llm.retries = 0
        config.agents.max_concurrent = 4 if variant == "beam-parallel" else 1
        if variant == "single-shot":
            config.budget.max_llm_calls = config.budget.max_candidates = 1
        algorithm = (
            "beam"
            if variant.startswith("beam-")
            else "baseline"
            if variant == "single-shot"
            else variant
        )
        search = SearchOrchestrator(
            problem,
            config,
            algorithm,
            client=FakeLLM({"default": ["print(sum(map(int,input().split())))"]}),
            evaluator=PublicEvaluator(grader, None),
        )
        result = await search.run()
        grade = (
            (
                await grader.grade(
                    result["candidate"]["code"], problem, None, '[{"input":"2 3","output":"5"}]'
                )
            ).model_dump()
            if result["candidate"]
            else {"passed": False, "status": "NO_CANDIDATE"}
        )
        rows.append(
            dict(
                **result,
                variant=variant,
                problem_id=problem.problem_id,
                trial=0,
                first_visible_reward=1,
                grade=grade,
                difficulty="fixture",
            )
        )
        save(output / "trials.json", rows)
    return generate(output)
