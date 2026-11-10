import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.live import Live
from rich.tree import Tree

from .benchmark import benchmark as run_benchmark
from .config import load_config
from .models import CodingProblem, SearchTree
from .search import POLICIES, SearchOrchestrator

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def solve(
    problem: Annotated[Path, typer.Option(exists=True)],
    algorithm: str = "beam",
    config: Path | None = None,
    parallel_agents: int | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    try:
        settings = load_config(config)
        if algorithm not in POLICIES:
            raise ValueError(f"Algorithm must be one of {', '.join(POLICIES)}")
        if parallel_agents is not None:
            if parallel_agents < 1 or (algorithm in {"mcts", "baseline"} and parallel_agents != 1):
                raise ValueError("Invalid concurrency for selected algorithm")
            settings.agents.max_concurrent = parallel_agents
        if provider:
            settings.llm.provider = provider
        if model:
            settings.llm.model = model
        visible = CodingProblem.model_validate(yaml.safe_load(problem.read_text())).visible()
        orchestrator = SearchOrchestrator(visible, settings, algorithm)

        async def execute() -> dict:
            with Live(console=console, refresh_per_second=4) as live:
                task = asyncio.create_task(orchestrator.run())
                try:
                    while not task.done():
                        live.update(
                            f"{algorithm} | frontier {orchestrator.frontier_index} | "
                            f"workers {orchestrator.pool.slots.active} | "
                            f"calls {orchestrator.budget.calls} | "
                            f"tokens {orchestrator.budget.input_tokens + orchestrator.budget.output_tokens}"
                        )
                        await asyncio.sleep(0.1)
                    return await task
                except asyncio.CancelledError:
                    task.cancel()
                    return await task

        result = asyncio.run(execute())
        console.print(result)
        console.print(f"Artifacts: {orchestrator.events.directory}")
        if result["termination_reason"] == "ERROR":
            raise typer.Exit(1)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def inspect(run_id: str, runs_dir: Path = Path("runs")) -> None:
    directory = runs_dir / run_id
    try:
        tree = SearchTree.model_validate_json((directory / "tree.json").read_text())
        result = (
            json.loads((directory / "result.json").read_text())
            if (directory / "result.json").exists()
            else {}
        )
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    display = Tree(f"Run {run_id}")
    branches = {"root": display}
    for node in sorted(tree.nodes.values(), key=lambda n: n.order):
        if node.parent_id is None:
            continue
        selected = " SELECTED" if node.node_id == result.get("selected_node_id") else ""
        label = (
            f"{node.node_id}: {node.candidate.strategy if node.candidate else ''} "
            f"reward={node.evaluation.reward if node.evaluation else None} {node.status} "
            f"depth={node.depth} worker={node.worker_id} visits={node.visits} "
            f"mean={node.total_reward / node.visits if node.visits else 0:.3f}{selected}"
        )
        branches[node.node_id] = branches[node.parent_id].add(label)
    console.print(display)
    console.print(result.get("budget", {}), result.get("concurrency", {}))


@app.command()
def benchmark(
    suite: Annotated[Path, typer.Option(exists=True)],
    algorithms: str = "baseline,best-of-n,beam,mcts",
    config: Path | None = None,
) -> None:
    try:
        selected = algorithms.split(",")
        if any(name not in POLICIES for name in selected):
            raise ValueError("Unknown benchmark algorithm")
        report = asyncio.run(run_benchmark(suite, selected, load_config(config)))
        console.print(report)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def experiment_prepare(
    cache: Path, manifest: Path, size: int = 100, seed: int = 42, download_data: bool = False
) -> None:
    """Create a deterministic public-only selection manifest from pinned JSONL files."""
    from .experiments.dataset import DATASET_REVISION, RELEASE, download, load_public, select
    from .experiments.runner import save

    if download_data:
        download(cache)
    problems, hashes, exclusions = load_public(cache)
    selected = select(problems, size, seed)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if manifest.exists():
        raise typer.BadParameter("Manifest exists; choose a new path to preserve selection")
    save(
        manifest,
        {
            "dataset_revision": DATASET_REVISION,
            "release": RELEASE,
            "seed": seed,
            "file_hashes": hashes,
            "exclusions": exclusions,
            "selection": "equal joint difficulty/source/month strata",
            "problems": [p.model_dump(mode="json") for p in selected],
        },
    )
    console.print(f"Saved {len(selected)} public problems to {manifest}")


@app.command()
def experiment_plan(config: Path) -> None:
    """Show request and conservative spending ceilings without making API calls."""
    from .experiments.runner import ExperimentConfig, preflight

    settings = ExperimentConfig.model_validate(yaml.safe_load(config.read_text()))
    console.print(preflight(settings, settings.problem_count))


@app.command()
def experiment_run(
    config: Path, manifest: Path, cache: Path, output: Path, allow_paid: bool = False
) -> None:
    """Run or resume a frozen experiment; requires explicit paid execution opt-in."""
    from .experiments.runner import ExperimentConfig, run

    settings = ExperimentConfig.model_validate(yaml.safe_load(config.read_text()))
    console.print(asyncio.run(run(settings, manifest, cache, output, allow_paid)))


@app.command()
def experiment_report(directory: Path) -> None:
    """Regenerate Markdown, HTML, CSV and figures from recorded trials."""
    from .experiments.report import generate

    console.print(generate(directory))


@app.command()
def experiment_fixture(
    output: Path = Path("runs/experiment-fixture"), runs_dir: Path = Path("runs")
) -> None:
    """Run a labeled fake-provider demonstration through the official Docker checker."""
    from .experiments.fixture import fixture

    console.print(asyncio.run(fixture(output, runs_dir)))
