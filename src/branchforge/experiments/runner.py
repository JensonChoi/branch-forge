import asyncio
import fcntl
import hashlib
import json
import platform
import subprocess
import time
from contextlib import ExitStack
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from ..config import Config, Settings
from ..execution import DockerExecutor
from ..llm import LiteLLMClient
from ..models import SearchTree, now
from ..search import SearchOrchestrator
from .dataset import DATASET_REVISION, GRADER_REVISION, RELEASE, Problem, private_row
from .grading import OfficialGrader, PublicEvaluator
from .report import aggregate, generate
from .spending import SpendingClient

Variant = Literal[
    "baseline", "best-of-n", "beam-sequential", "beam-parallel", "mcts", "single-shot"
]
VARIANTS: tuple[Variant, ...] = (
    "baseline",
    "best-of-n",
    "beam-sequential",
    "beam-parallel",
    "mcts",
    "single-shot",
)


class ExperimentConfig(Settings):
    search: Config = Field(default_factory=Config)
    stage: Literal["smoke", "validation", "pilot", "primary"] = "validation"
    trials: int = Field(default=1, ge=1)
    seed: int = 42
    grader_image: str = "branchforge-lcb:28fef95"
    model_training_cutoff: str | None = None
    # Conservative per-request upper-bound rates, including any provider surcharge.
    input_usd_per_million: float = Field(default=0.75, gt=0)
    output_usd_per_million: float = Field(default=4.5, gt=0)
    spending_limit_usd: float | None = Field(default=None, gt=0)
    spending_mode: Literal["preflight", "per_request"] = "preflight"
    variants: tuple[
        Literal["baseline", "best-of-n", "beam-sequential", "beam-parallel", "mcts", "single-shot"],
        ...,
    ] = VARIANTS
    spending_ledger_path: Path | None = None

    @model_validator(mode="after")
    def valid_variants(self) -> "ExperimentConfig":
        if not self.variants or len(set(self.variants)) != len(self.variants):
            raise ValueError("Variants must be nonempty and unique")
        return self


def save(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str))
    temporary.replace(path)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def preflight(config: ExperimentConfig, count: int) -> dict[str, Any]:
    attempts = count * config.trials * len(config.variants)
    calls = (
        count
        * config.trials
        * sum(
            1 if variant == "single-shot" else config.search.budget.max_llm_calls
            for variant in config.variants
        )
    )
    # UTF-8 bytes bound text tokens; allowance for chat framing. No tools/images used.
    input_bound = 4 * config.search.llm.max_prompt_chars + 4096
    cost = (
        calls
        * (
            input_bound * config.input_usd_per_million
            + config.search.llm.max_output_tokens * config.output_usd_per_million
        )
        / 1e6
    )
    return {
        "problem_count": count,
        "trials": attempts,
        "physical_request_ceiling": calls,
        "conservative_cost_ceiling_usd": cost,
        "spending_limit_usd": config.spending_limit_usd,
        "spending_mode": config.spending_mode,
        "assumption": "Configured rates must upper-bound actual provider rates; text-only calls.",
    }


async def _run(
    config: ExperimentConfig,
    manifest_path: Path,
    cache: Path,
    output: Path,
    allow_paid: bool = False,
) -> dict[str, Any]:
    selection = json.loads(manifest_path.read_text())
    if selection["dataset_revision"] != DATASET_REVISION or selection["release"] != RELEASE:
        raise ValueError("Unsupported dataset pin")
    stage_size = {"smoke": 2, "validation": 20, "pilot": 50, "primary": 100}[config.stage]
    problems = [Problem.model_validate(p) for p in selection["problems"]][:stage_size]
    if len({p.question_id for p in problems}) != len(problems):
        raise ValueError("Manifest contains duplicate problem IDs")
    if len(problems) != stage_size:
        raise ValueError(f"Stage requires {stage_size} selected problems")
    if config.search.llm.provider == "fake":
        raise ValueError(
            "Use fixture tests for fake providers; benchmark CLI requires a real model"
        )
    estimate = preflight(config, len(problems))
    if not allow_paid:
        raise ValueError("Paid execution requires --allow-paid after reviewing experiment-plan")
    if config.spending_limit_usd is None or (
        config.spending_mode == "preflight"
        and estimate["conservative_cost_ceiling_usd"] > config.spending_limit_usd
    ):
        raise ValueError("Conservative request ceiling exceeds configured spending limit")
    # Verify cache bytes before any paid requests. Never decode private payloads here.
    for name, expected in selection["file_hashes"].items():
        with (cache / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError("Dataset cache checksum mismatch")
    executor = DockerExecutor(
        config.search.execution.model_copy(update={"image": config.grader_image})
    )
    await executor.check()
    rc, label, _ = await executor.command(
        "image",
        "inspect",
        "--format",
        '{{index .Config.Labels "org.branchforge.grader.revision"}}',
        config.grader_image,
    )
    if rc or label.strip() != GRADER_REVISION:
        raise ValueError("Grader image revision mismatch")
    rc, image_id, _ = await executor.command(
        "image", "inspect", "--format", "{{.Id}}", config.grader_image
    )
    if rc:
        raise ValueError("Cannot identify grader image")
    code_revision = (
        await asyncio.to_thread(subprocess.check_output, ["git", "rev-parse", "HEAD"], text=True)
    ).strip()
    manifest = {
        "schema_version": 1,
        "stage": config.stage,
        "fixture": False,
        "selection_hash": fingerprint(selection),
        "problem_ids": [p.question_id for p in problems],
        "dataset_revision": DATASET_REVISION,
        "release": RELEASE,
        "grader_revision": GRADER_REVISION,
        "grader_image_id": image_id.strip(),
        "versions": {
            name: version(name) for name in ("branchforge", "litellm", "pydantic", "matplotlib")
        },
        "config": config.model_dump(mode="json"),
        "expected_trials": estimate["trials"],
        "estimate": estimate,
        "python": platform.python_version(),
        "code_revision": code_revision,
        "source_hash": fingerprint(
            {
                str(p.relative_to(Path(__file__).parents[1])): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted(Path(__file__).parents[1].rglob("*.py"))
            }
        ),
        "contamination": "risk-aware; training cutoff does not establish non-exposure",
    }
    output.mkdir(parents=True, exist_ok=True)
    manifest_file = output / "manifest.json"
    if manifest_file.exists():
        if json.loads(manifest_file.read_text()) != manifest:
            raise ValueError("Resume protocol differs from frozen manifest; use a new experiment")
    else:
        save(manifest_file, manifest)
    trials_file = output / "trials.json"
    rows = json.loads(trials_file.read_text()) if trials_file.exists() else []
    if any(
        r["variant"] not in config.variants
        or r["problem_id"] not in {p.question_id for p in problems}
        for r in rows
    ):
        raise ValueError("Saved trials do not match scheduled problems/variants")
    completed = {(r["problem_id"], r["variant"], r["trial"]) for r in rows}
    if not trials_file.exists():
        save(trials_file, rows)
    spending_client = (
        SpendingClient(
            LiteLLMClient(),
            config.spending_ledger_path or output / "spending.json",
            config.spending_limit_usd,
            config.input_usd_per_million,
            config.output_usd_per_million,
        )
        if config.spending_mode == "per_request"
        else None
    )
    if spending_client:
        save(output / "spending.json", spending_client.state)
    grader = OfficialGrader(executor)
    for trial in range(config.trials):
        for problem in problems:
            for variant in config.variants:
                identity = (problem.question_id, variant, trial)
                if identity in completed:
                    continue
                if spending_client and spending_client.exhausted:
                    return generate(output)
                checkpoint = output / (fingerprint(identity) + ".selected.json")
                if checkpoint.exists():
                    row = json.loads(checkpoint.read_text())
                else:
                    marker = checkpoint.with_suffix(".started")
                    if marker.exists():
                        run_id = marker.read_text().strip()
                        artifact = config.search.runs_dir / run_id
                        if (artifact / "result.json").exists():
                            result = json.loads((artifact / "result.json").read_text())
                        else:
                            # Never regenerate a partially dispatched trial on resume.
                            result = {
                                "run_id": run_id,
                                "candidate": None,
                                "visible_reward": None,
                                "termination_reason": "INTERRUPTED",
                                "budget": {
                                    "llm_calls": None,
                                    "input_tokens": None,
                                    "output_tokens": None,
                                    "total_tokens": None,
                                    "cost_usd": None,
                                    "candidates": None,
                                    "evaluations": None,
                                    "elapsed_seconds": None,
                                },
                            }
                    else:
                        settings = config.search.model_copy(deep=True)
                        settings.seed = config.seed + trial
                        settings.agents.max_concurrent = (
                            config.search.agents.max_concurrent
                            if variant in {"beam-parallel", "best-of-n"}
                            else 1
                        )
                        if variant == "single-shot":
                            settings.budget.max_llm_calls = settings.budget.max_candidates = 1
                        algorithm = (
                            "beam"
                            if variant.startswith("beam-")
                            else "baseline"
                            if variant == "single-shot"
                            else variant
                        )
                        evaluator = PublicEvaluator(
                            OfficialGrader(
                                DockerExecutor(
                                    config.search.execution.model_copy(
                                        update={"image": config.grader_image}
                                    )
                                )
                            ),
                            problem.function_name,
                        )
                        client_options = {"client": spending_client} if spending_client else {}
                        search = SearchOrchestrator(
                            problem.visible(),
                            settings,
                            algorithm,
                            evaluator=evaluator,
                            **client_options,
                        )
                        marker.write_text(search.run_id)
                        result = await search.run()
                    artifact = config.search.runs_dir / result["run_id"]
                    tree = (
                        SearchTree.model_validate_json((artifact / "tree.json").read_text())
                        if (artifact / "tree.json").exists()
                        else SearchTree()
                    )
                    event_path = artifact / "events.jsonl"
                    event_rows = (
                        [json.loads(line) for line in event_path.read_text().splitlines()]
                        if event_path.exists()
                        else []
                    )
                    first_evaluation = next(
                        (e for e in event_rows if e.get("event_type") == "CANDIDATE_EVALUATED"),
                        None,
                    )
                    candidates = [n.candidate.code for n in tree.nodes.values() if n.candidate]
                    row = dict(
                        **result,
                        problem_id=problem.question_id,
                        variant=variant,
                        trial=trial,
                        difficulty=problem.difficulty,
                        platform=problem.platform,
                        first_visible_reward=first_evaluation.get("reward")
                        if first_evaluation
                        else None,
                        frontier_count=sum(
                            e.get("event_type") == "FRONTIER_COMPLETED" for e in event_rows
                        ),
                        pruning_rate=sum(n.status == "PRUNED" for n in tree.nodes.values())
                        / max(1, len(candidates)),
                        duplicate_candidates=len(candidates) - len(set(candidates)),
                        recorded_at=now().isoformat(),
                        max_depth=max(n.depth for n in tree.nodes.values()),
                    )
                    row["selected_code_sha256"] = hashlib.sha256(
                        (row["candidate"]["code"] if row["candidate"] else "").encode()
                    ).hexdigest()
                    save(checkpoint, row)
                    if row.get("termination_reason") == "USER_CANCELED":
                        raise asyncio.CancelledError
                candidate = row["candidate"]
                grade_started = time.monotonic()
                if candidate:
                    raw = private_row(cache, problem.question_id)
                    grade = await grader.grade(
                        candidate["code"],
                        problem.visible(),
                        problem.function_name,
                        raw["private_test_cases"],
                    )
                    row["grade"] = grade.model_dump()
                else:
                    row["grade"] = {
                        "passed": None if row.get("termination_reason") == "INTERRUPTED" else False,
                        "status": "INTERRUPTED"
                        if row.get("termination_reason") == "INTERRUPTED"
                        else "NO_CANDIDATE",
                    }
                row["grading_seconds"] = time.monotonic() - grade_started
                if spending_client:
                    save(output / "spending.json", spending_client.state)
                rows.append(row)
                save(trials_file, rows)
                save(
                    output / "summary.json",
                    aggregate(rows)
                    | {
                        "stage": config.stage,
                        "fixture": False,
                        "expected_trials": estimate["trials"],
                        "completed_trials": len(rows),
                    },
                )
    return generate(output)


async def run(
    config: ExperimentConfig,
    manifest_path: Path,
    cache: Path,
    output: Path,
    allow_paid: bool = False,
) -> dict[str, Any]:
    """Exclusive process lock prevents concurrent resume from spending twice."""
    output.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        paths = [output / ".lock"]
        if config.spending_mode == "per_request":
            paths.append(
                (config.spending_ledger_path or output / "spending.json").with_suffix(".lock")
            )
        for path in paths:
            lock = stack.enter_context(path.open("a"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Experiment or shared spending ledger is already running") from exc
        return await _run(config, manifest_path, cache, output, allow_paid)
