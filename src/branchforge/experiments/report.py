"""Reports derived exclusively from saved trials; problem-cluster bootstrap intervals."""

import csv
import html
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def wilson(successes: int, n: int) -> list[float] | None:
    if not n:
        return None
    z = 1.959963984540054
    p = successes / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0, center - radius), min(1, center + radius)]


def bootstrap(values: list[float], seed: int = 42) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    samples = [mean(rng.choices(values, k=len(values))) for _ in range(2000)]
    return [quantile(samples, 0.025), quantile(samples, 0.975)]


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["variant"]].append(row)
    metrics = {}
    for variant, group in sorted(groups.items()):
        solved = sum(r["grade"]["passed"] is True for r in group)
        opportunities = [
            r
            for r in group
            if r.get("first_visible_reward") is not None and r["first_visible_reward"] < 1
        ]
        costs = [r["budget"]["cost_usd"] for r in group]
        total_cost = sum(costs) if all(c is not None for c in costs) else None
        clusters: dict[str, list[float]] = defaultdict(list)
        for r in group:
            clusters[r["problem_id"]].append(float(r["grade"]["passed"] is True))
        metrics[variant] = m = {
            "trials": len(group),
            "problems": len(clusters),
            "solved": solved,
            "solve_rate": solved / len(group),
            "solve_ci95": (
                wilson(solved, len(group))
                if len(clusters) == len(group)
                else bootstrap([mean(v) for v in clusters.values()])
            ),
            "unknown_grades": sum(r["grade"]["passed"] is None for r in group),
            "visible_success_rate": mean(r["visible_reward"] == 1 for r in group),
            "recovery_opportunities": len(opportunities),
            "recovery_rate": (
                mean(r["grade"]["passed"] is True for r in opportunities) if opportunities else None
            ),
            "total_cost_usd": total_cost,
            "cost_per_solved": total_cost / solved if total_cost is not None and solved else None,
            "cost_per_attempt": total_cost / len(group) if total_cost is not None else None,
            "failures": dict(Counter(r["grade"]["status"] for r in group)),
        }
        m["behavior"] = {}
        for behavior in ("max_depth", "frontier_count", "pruning_rate", "duplicate_candidates"):
            observed = [r[behavior] for r in group if r.get(behavior) is not None]
            m["behavior"][behavior] = mean(observed) if observed else None
        for behavior in ("max_subagents", "average_active_subagents"):
            observed = [r.get("concurrency", {}).get(behavior) for r in group]
            m["behavior"][behavior] = (
                mean(observed) if all(v is not None for v in observed) else None
            )
        for key in (
            "physical_requests",
            "logical_generations",
            "retry_requests",
            "failed_requests",
            "reasoning_tokens",
            "llm_calls",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "candidates",
            "evaluations",
            "elapsed_seconds",
            "cost_usd",
        ):
            values = [r["budget"].get(key) for r in group]
            m[key] = (
                {"mean": mean(values), "median": median(values), "p95": quantile(values, 0.95)}
                if all(v is not None for v in values)
                else None
            )
    paired = []
    for a, b in itertools.combinations(sorted(groups), 2):
        indexed = [{(r["problem_id"], r["trial"]): r for r in groups[v]} for v in (a, b)]
        keys = sorted(indexed[0].keys() & indexed[1].keys())
        differences: dict[str, list[float]] = defaultdict(list)
        counts: Counter[str] = Counter()
        for pair_key in keys:
            x, y = [g[pair_key]["grade"]["passed"] is True for g in indexed]
            differences[pair_key[0]].append(float(x) - float(y))
            counts["both" if x and y else "only_a" if x else "only_b" if y else "neither"] += 1
        values = [mean(v) for v in differences.values()]
        resources = {}
        for resource in ("elapsed_seconds", "total_tokens", "cost_usd"):
            resource_clusters: dict[str, list[float]] = defaultdict(list)
            for pair_key in keys:
                x_value, y_value = [g[pair_key]["budget"].get(resource) for g in indexed]
                if x_value is not None and y_value is not None:
                    resource_clusters[pair_key[0]].append(x_value - y_value)
            resource_values = [mean(v) for v in resource_clusters.values()]
            resources[resource] = {
                "paired_problems": len(resource_values),
                "difference": mean(resource_values) if resource_values else None,
                "ci95": bootstrap(resource_values),
            }
        paired.append(
            {
                "a": a,
                "b": b,
                "paired_trials": len(keys),
                "paired_problems": len(values),
                "difference": mean(values) if values else None,
                "ci95": bootstrap(values),
                "counts": dict(counts),
                "resources": resources,
            }
        )
    difficulty: dict[str, Any] = {}
    for level in sorted({r.get("difficulty", "unknown") for r in rows}):
        difficulty[level] = {}
        for variant, group_rows in groups.items():
            subset = [r for r in group_rows if r.get("difficulty", "unknown") == level]
            if subset:
                difficulty[level][variant] = {
                    "attempts": len(subset),
                    "solve_rate": mean(r["grade"]["passed"] is True for r in subset),
                }
    return {"metrics": metrics, "paired": paired, "difficulty": difficulty}


def generate(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text())
    rows = json.loads((directory / "trials.json").read_text())
    summary = aggregate(rows)
    summary.update(
        stage=manifest["stage"],
        fixture=manifest["fixture"],
        expected_trials=manifest["expected_trials"],
        completed_trials=len(rows),
    )
    if (directory / "spending.json").exists():
        ledger = json.loads((directory / "spending.json").read_text())
        summary["spending"] = {
            "limit_usd": ledger["limit_micro_usd"] / 1e6,
            "accounted_upper_cost_usd": sum(r["accounted_micro_usd"] for r in ledger["requests"])
            / 1e6,
            "exhausted": ledger["exhausted"],
            "unresolved_requests": sum(r["status"] != "returned" for r in ledger["requests"]),
        }
    (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    lines = [
        "# BranchForge: Evaluating Tree-Search-Based LLM Agents on LiveCodeBench",
        "",
        "**DETERMINISTIC FIXTURE — not model performance.**"
        if manifest["fixture"]
        else "Real-model experiment; correctness uses the official final checker.",
        "",
        f"Stage: {manifest['stage']}. Completed {len(rows)}/{manifest['expected_trials']} trials.",
        "",
        "## Abstract",
        "",
        (
            f"This {manifest['stage']} experiment records {len(rows)} of {manifest['expected_trials']} scheduled trials. "
            "We compare feedback-guided search with trajectory and sampling baselines using official final grading. "
            "The tables quantify observed correctness and compute; they do not establish a general advantage for search."
        ),
        "",
        "## Introduction and research questions",
        "",
        (
            "Explicit branching can preserve alternatives when a single trajectory fails. This study asks whether "
            "that helps correctness and recovery, whether parallel beam reduces latency, which methods offer favorable "
            "accuracy/cost tradeoffs, and how outcomes vary by difficulty. Related work includes "
            "[Tree of Thoughts](https://arxiv.org/abs/2305.10601) and "
            "[Language Agent Tree Search](https://arxiv.org/abs/2310.04406)."
        ),
        "",
        "## Methodology and reproducibility",
        "",
        "```json",
        json.dumps(manifest, indent=2),
        "```",
        "",
        "## Results",
        "",
        "| Algorithm | Solved / attempts | Solve rate (95% CI) | Cost / solve | Recovery |",
        "|---|---:|---|---:|---|",
    ]
    for name, m in summary["metrics"].items():
        lines.append(
            f"| {name} | {m['solved']} / {m['trials']} | {m['solve_rate']:.3f} "
            f"{m['solve_ci95']} | {m['cost_per_solved'] if m['cost_per_solved'] is not None else 'unknown / undefined'} "
            f"| {m['recovery_rate']} (n={m['recovery_opportunities']}) |"
        )
    lines += [
        "",
        "## Paired comparisons",
        "",
        "```json",
        json.dumps(summary["paired"], indent=2),
        "```",
        "",
        "## Interpretation and limitations",
        "",
        (
            "No superiority claim is generated automatically. Missing official grades count as "
            "unsolved in end-to-end rates and are separately reported. Incomplete experiments "
            "must not be interpreted as the primary study."
        ),
        "",
        (
            "Single-trial proportions use Wilson intervals; repeated trials and paired differences "
            "use 2,000 problem-cluster bootstrap draws (seed 42). Comparisons are exploratory. "
            "Repeated trials are not independent problems. Shared ceilings do not imply equal "
            "realized compute; early stopping and wall-time censoring affect resource comparisons."
        ),
        "",
        (
            "Contamination-risk-aware, not contamination-free. No verified uncontaminated subset "
            "is claimed. Algorithmic category metadata is unavailable. Lite test suites are used."
        ),
        "",
        (
            "First-attempt official correctness is unavailable unless the first candidate was "
            "selected: only the frozen final candidate is privately graded."
        ),
        "",
        "## Case studies",
        "",
    ]
    case_directory = directory / "case_studies"
    case_directory.mkdir(exist_ok=True)
    # Prefer disagreements, then cover distinct problems; never call these a random sample.
    by_problem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_problem[row["problem_id"]].append(row)
    case_ids = sorted(
        by_problem, key=lambda key: (-len({r["grade"]["passed"] for r in by_problem[key]}), key)
    )[:5]
    case_rows = [r for key in case_ids for r in by_problem[key]]
    for index, row in enumerate(case_rows):
        lines += [
            (
                f"- {row['problem_id']} / {row['variant']}: {row['grade']['status']}; "
                f"[search replay](/runs/{row['run_id']}). "
                "Conceptual failure causes require manual review."
            )
        ]
        case_text = f"# {row['problem_id']} / {row['variant']}\n\n" + json.dumps(
            {
                k: row.get(k)
                for k in (
                    "difficulty",
                    "first_visible_reward",
                    "visible_reward",
                    "grade",
                    "budget",
                    "concurrency",
                    "max_depth",
                    "candidate",
                )
            },
            indent=2,
        )
        (case_directory / f"case-{index:03d}.md").write_text(case_text)
    lines += [
        "",
        "## Difficulty breakdown",
        "",
        "```json",
        json.dumps(summary.get("difficulty", {}), indent=2),
        "```",
        "",
        "## Search behavior and resources",
        "",
        "```json",
        json.dumps(summary["metrics"], indent=2),
        "```",
    ]
    from .figures import figures

    paths = figures(directory, summary, rows) if rows else []
    lines += ["", "## Figures", ""] + [f"![{Path(p).stem}]({p})" for p in paths]
    lines += [
        "",
        "## Discussion and conclusion",
        "",
        (
            "Interpret paired differences with their intervals, missingness, actual resource use, and pilot status. "
            "Case studies prioritize observed disagreements and describe candidate behavior, not internal model reasoning. "
            "No causal or contamination-free claim follows from these measurements."
        ),
    ]
    (directory / "configuration.json").write_text(json.dumps(manifest.get("config", {}), indent=2))
    (directory / "problem_manifest.json").write_text(
        json.dumps(manifest.get("problem_ids", []), indent=2)
    )
    markdown = "\n".join(lines) + "\n"
    (directory / "report.md").write_text(markdown)
    import markdown as markdown_renderer

    # Escape all input before rendering so generated code cannot introduce HTML.
    rendered = markdown_renderer.markdown(
        html.escape(markdown), extensions=["tables", "fenced_code"]
    )
    (directory / "report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>BranchForge benchmark report</title>'
        "<style>body{max-width:1100px;margin:40px auto;padding:20px;font:16px/1.6 system-ui;color:#172333}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6fa;padding:16px}"
        "table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ccd3de}"
        "img{max-width:100%}h1,h2{line-height:1.2}</style>" + rendered
    )
    with (directory / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "problem_id",
                "variant",
                "trial",
                "run_id",
                "passed",
                "status",
                "tokens",
                "cost_usd",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {k: r[k] for k in ("problem_id", "variant", "trial", "run_id")}
                | {
                    "passed": r["grade"]["passed"],
                    "status": r["grade"]["status"],
                    "tokens": r["budget"]["total_tokens"],
                    "cost_usd": r["budget"]["cost_usd"],
                }
            )
    (directory / "per_problem_results.csv").write_bytes((directory / "results.csv").read_bytes())
    bars = []
    for i, (name, m) in enumerate(summary["metrics"].items()):
        y = 30 + i * 40
        bars.append(
            f'<text x="5" y="{y + 15}">{html.escape(name)}</text>'
            f'<rect x="190" y="{y}" width="{m["solve_rate"] * 350}" height="24" fill="#3671bd"/>'
            f'<text x="550" y="{y + 15}">{m["solve_rate"]:.1%}</text>'
        )
    (directory / "solve-rates.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="650" height="300">'
        '<rect width="100%" height="100%" fill="white"/>' + "".join(bars) + "</svg>"
    )
    return summary
