"""Publication-exportable figures derived from persisted measurements."""

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt


def figures(directory: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    target = directory / "figures"
    target.mkdir(exist_ok=True)
    metrics = summary["metrics"]
    names = list(metrics)
    paths = []

    def finish(fig: Any, name: str) -> None:
        fig.tight_layout()
        fig.savefig(target / f"{name}.svg")
        fig.savefig(target / f"{name}.png", dpi=160)
        plt.close(fig)
        paths.append(f"figures/{name}.svg")

    fig, ax = plt.subplots(figsize=(9, 4))
    values = [metrics[n]["solve_rate"] for n in names]
    errors = [
        [max(0, v - metrics[n]["solve_ci95"][0]) for n, v in zip(names, values, strict=True)],
        [max(0, metrics[n]["solve_ci95"][1] - v) for n, v in zip(names, values, strict=True)],
    ]
    ax.barh(names, values, xerr=errors, capsize=3)
    ax.set(xlabel="End-to-end solve rate (95% CI)", xlim=(0, 1))
    finish(fig, "solve-rates")
    for metric, title in (
        ("elapsed_seconds", "Latency (seconds)"),
        ("total_tokens", "Total tokens"),
        ("cost_usd", "API cost (USD)"),
    ):
        fig, ax = plt.subplots(figsize=(9, 4))
        groups = [
            [
                r["budget"].get(metric)
                for r in rows
                if r["variant"] == name and r["budget"].get(metric) is not None
            ]
            for name in names
        ]
        eligible = [(n, g) for n, g in zip(names, groups, strict=True) if g]
        if eligible:
            ax.boxplot(
                [g for _, g in eligible],
                tick_labels=[n for n, _ in eligible],
                orientation="horizontal",
            )
        else:
            ax.text(0.5, 0.5, "Measurements unavailable", ha="center", transform=ax.transAxes)
        ax.set_xlabel(title)
        finish(fig, metric)
    for metric, label in (
        ("cost_usd", "Mean observed cost (USD)"),
        ("total_tokens", "Mean observed tokens"),
    ):
        fig, ax = plt.subplots(figsize=(8, 4))
        for name, m in metrics.items():
            if m.get(metric):
                x, y = m[metric]["mean"], m["solve_rate"]
                ax.scatter(x, y)
                ax.annotate(name, (x, y))
        ax.set(xlabel=label, ylabel="Solve rate", ylim=(0, 1))
        finish(fig, f"accuracy-{metric}")
    fig, ax = plt.subplots(figsize=(9, 4))
    eligible = [
        (n, m["recovery_rate"]) for n, m in metrics.items() if m["recovery_rate"] is not None
    ]
    if eligible:
        ax.barh([n for n, _ in eligible], [v for _, v in eligible])
    ax.set(xlabel="Recovery rate (denominators in results table)", xlim=(0, 1))
    finish(fig, "recovery")
    return paths
