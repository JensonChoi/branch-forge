import platform
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from .config import Config
from .execution import DockerExecutor, Evaluator
from .models import Candidate, CodingProblem, TestCase, uid
from .runtime import Events
from .search import SearchOrchestrator


async def benchmark(suite: Path, algorithms: list[str], config: Config) -> dict[str, Any]:
    specification = yaml.safe_load(suite.read_text())
    report = Events(config.runs_dir / ("benchmark-" + uid()), "benchmark")
    rows = []
    # Hidden fixture contents are loaded only after final selection.
    for repetition in range(specification.get("repeats", 1)):
        for entry in specification["problems"]:
            problem = CodingProblem.model_validate(
                yaml.safe_load(Path(entry["problem"]).read_text())
            ).visible()
            for algorithm in algorithms:
                variants = [(algorithm, config.agents.max_concurrent)]
                if algorithm == "beam":
                    variants = [
                        ("beam-sequential", 1),
                        ("beam-parallel", config.agents.max_concurrent),
                    ]
                for label, concurrency in variants:
                    settings = config.model_copy(deep=True)
                    settings.agents.max_concurrent = concurrency
                    search = SearchOrchestrator(problem, settings, algorithm)
                    result = await search.run()
                    hidden_reward = None
                    if result["candidate"]:
                        tests = tuple(
                            TestCase.model_validate(t)
                            for t in yaml.safe_load(Path(entry["hidden"]).read_text())
                        )
                        if not tests:
                            raise ValueError("Benchmark requires held-out tests")
                        held_out = problem.model_copy(update={"visible_tests": tests})
                        evaluation = await Evaluator(DockerExecutor(settings.execution)).evaluate(
                            Candidate.model_validate(result["candidate"]), held_out
                        )
                        hidden_reward = evaluation.reward
                    rows.append(
                        dict(
                            problem_id=problem.problem_id,
                            variant=label,
                            repetition=repetition,
                            held_out_reward=hidden_reward,
                            **result,
                        )
                    )
                    report.save("trials.json", rows)
    metrics = {}
    for label in sorted({row["variant"] for row in rows}):
        group = [row for row in rows if row["variant"] == label]
        metrics[label] = {
            "trials": len(group),
            "held_out_pass_rate": mean(row["held_out_reward"] == 1 for row in group),
            "visible_success_rate": mean(row["visible_reward"] == 1 for row in group),
            "infrastructure_or_run_errors": sum(
                row["termination_reason"] == "ERROR" for row in group
            ),
            "mean_llm_calls": mean(row["budget"]["llm_calls"] for row in group),
            "mean_input_tokens": mean(row["budget"]["input_tokens"] for row in group),
            "mean_output_tokens": mean(row["budget"]["output_tokens"] for row in group),
            "mean_latency": mean(row["budget"]["elapsed_seconds"] for row in group),
            "mean_evaluations": mean(row["budget"]["evaluations"] for row in group),
            "mean_depth": mean(row["average_depth"] for row in group),
            "max_workers": max(row["concurrency"]["max_subagents"] for row in group),
            "mean_cost_usd": (
                mean(row["budget"]["cost_usd"] for row in group)
                if all(row["budget"]["cost_usd"] is not None for row in group)
                else None
            ),
            "termination_reasons": dict(Counter(row["termination_reason"] for row in group)),
        }
    summary = {
        "metrics": metrics,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": {name: version(name) for name in ["branchforge", "litellm", "pydantic"]},
        "config": config.model_dump(mode="json"),
        "artifact_path": str(report.directory),
    }
    report.save("summary.json", summary)
    return summary
