"""Artifact adapters. No candidate code is imported or executed."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from branchforge.models import SearchTree

from .schemas import (
    Envelope,
    RunDetail,
    RunMetricsResponse,
    RunPage,
    SearchEventResponse,
    SearchTreeResponse,
    WorkerTimelineResponse,
)


class Response(BaseModel):
    data: Any
    warnings: list[str] = []


class Reader:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def directory(self, run_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            raise HTTPException(400, "Invalid run ID")
        path = (self.root / run_id).resolve()
        if not path.is_relative_to(self.root) or not path.is_dir():
            raise HTTPException(404, "Run not found")
        return path

    def read(self, directory: Path, name: str, warnings: list[str]) -> Any:
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or not path.is_relative_to(self.root):
            warnings.append(f"{name}: unsafe path")
            return {}
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            warnings.append(f"{name}: missing or invalid")
            return {}

    def events(self, directory: Path, warnings: list[str]) -> list[dict]:
        path = (directory / "events.jsonl").resolve()
        if not path.is_relative_to(directory):
            warnings.append("events.jsonl: unsafe path")
            return []
        events = []
        seen = set()
        try:
            for line in path.read_text().splitlines():
                try:
                    event = json.loads(line)
                    seq = event["sequence"]
                    if (
                        not isinstance(seq, int)
                        or seq in seen
                        or not isinstance(event.get("event_type"), str)
                    ):
                        raise ValueError()
                    SearchEventResponse.model_validate(event)
                    seen.add(seq)
                    events.append(event)
                except (ValueError, KeyError, TypeError, AttributeError):
                    warnings.append("Malformed or duplicate event omitted")
        except OSError:
            warnings.append("Events unavailable")
        events.sort(key=lambda e: e["sequence"])
        if [e["sequence"] for e in events] != list(range(1, len(events) + 1)):
            warnings.append("Event sequence has gaps")
        return events

    def summary(self, directory: Path, warnings: list[str]) -> dict:
        result = self.read(directory, "result.json", warnings)
        problem = self.read(directory, "problem.json", warnings)
        config = self.read(directory, "config.json", warnings)
        if not all(isinstance(x, dict) for x in (result, problem, config)):
            warnings.append("Invalid metadata shape")
            result, problem, config = {}, {}, {}
        reason = result.get("termination_reason")
        return {
            "run_id": directory.name,
            "title": problem.get("title", directory.name),
            "algorithm": result.get("algorithm"),
            "model": (config.get("llm") or {}).get("model")
            if isinstance(config.get("llm"), dict)
            else None,
            "status": "partial"
            if not reason
            else "canceled"
            if reason == "USER_CANCELED"
            else "failed"
            if reason == "ERROR"
            else "completed",
            "termination_reason": reason,
            "selected_node_id": result.get("selected_node_id"),
            "visible_reward": result.get("visible_reward"),
            "budget": {
                k: v
                for k, v in (result.get("budget") or {}).items()
                if k
                in {
                    "llm_calls",
                    "candidates",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "cost_usd",
                    "elapsed_seconds",
                    "evaluations",
                }
                and (v is None or isinstance(v, (int, float)))
            }
            if isinstance(result.get("budget"), dict)
            else {},
        }


def timeline(events: list[dict]) -> dict:
    opened: dict[tuple[str, str], dict] = {}
    intervals = []
    workers = {}
    task_frontiers = {
        e.get("task_id"): e.get("frontier_index")
        for e in events
        if e["event_type"] == "BRANCH_TASK_CREATED"
    }
    task_candidates: dict[str | None, str | None] = {}
    for e in events:
        if e["event_type"] == "CANDIDATE_GENERATED":
            task_candidates.setdefault(e.get("task_id"), e.get("candidate_id"))
    starts = {
        "BRANCH_TASK_QUEUED": "queued",
        "SUBAGENT_STARTED": "worker",
        "LLM_STARTED": "llm",
        "EVALUATION_STARTED": "evaluation",
        "SUBAGENT_REFINEMENT_STARTED": "refinement",
    }
    ends = {
        "SUBAGENT_STARTED": "queued",
        "LLM_FINISHED": "llm",
        "LLM_FAILED": "llm",
        "CANDIDATE_EVALUATED": "evaluation",
        "CANDIDATE_GENERATED": "refinement",
    }
    for event in events:
        task = event.get("task_id", "")
        kind = event["event_type"]
        if kind == "SUBAGENT_STARTED":
            workers[task] = event.get("worker_id", task)
        closing = ends.get(kind)
        if kind in {"SUBAGENT_FINISHED", "SUBAGENT_FAILED", "SUBAGENT_CANCELED"}:
            closing = "worker"
        if closing:
            keys = [(task, closing)]
            if closing == "worker":
                keys = [key for key in opened if key[0] == task]
            for key in keys:
                if key in opened:
                    interval = opened.pop(key)
                    interval.update(outcome=kind)
                    if key[1] == closing:
                        interval["end"] = event.get("timestamp")
                    intervals.append(interval)
        if kind in starts:
            activity = starts[kind]
            opened[(task, activity)] = {
                "task_id": task,
                "worker_id": workers.get(task, task),
                "kind": activity,
                "start": event.get("timestamp"),
                "end": None,
                "candidate_id": event.get("candidate_id"),
            }
    intervals.extend(opened.values())
    points = []
    busy = 0.0
    for interval in intervals:
        interval["worker_id"] = workers.get(interval["task_id"], interval["task_id"])
        interval["frontier_index"] = task_frontiers.get(interval["task_id"])
        interval["candidate_id"] = interval.get("candidate_id") or task_candidates.get(
            interval["task_id"]
        )
        if interval["kind"] == "worker" and interval["start"] and interval["end"]:
            try:
                a, b = (datetime.fromisoformat(interval[k]).timestamp() for k in ("start", "end"))
                if b >= a:
                    points.extend([(a, 1), (b, -1)])
                    busy += b - a
            except ValueError:
                pass
    active = peak = 0
    for _, delta in sorted(points):
        active += delta
        peak = max(peak, active)
    span = max((p[0] for p in points), default=0) - min((p[0] for p in points), default=0)
    return {
        "intervals": intervals,
        "peak_concurrency": peak if points else None,
        "busy_seconds": busy if points else None,
        "average_active": busy / span if span else None,
    }


def create_app(runs_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="BranchForge dashboard")
    reader = Reader(runs_dir or Path(os.environ.get("BRANCHFORGE_RUNS_DIR", "runs")))

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/runs", response_model=Envelope[RunPage])
    def runs(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)) -> Response:
        rows = []
        for path in sorted(reader.root.iterdir()) if reader.root.exists() else []:
            if (
                path.is_dir()
                and not path.name.startswith("benchmark-")
                and path.resolve().is_relative_to(reader.root)
            ):
                warnings: list[str] = []
                rows.append(reader.summary(path.resolve(), warnings) | {"warnings": warnings})
        return Response(data={"items": rows[offset : offset + limit], "total": len(rows)})

    @app.get("/api/runs/{run_id}", response_model=Envelope[RunDetail])
    def detail(run_id: str) -> Response:
        warnings: list[str] = []
        directory = reader.directory(run_id)
        data = reader.summary(directory, warnings)
        events = reader.events(directory, warnings)
        data["started_at"] = events[0].get("timestamp") if events else None
        data["held_out_reward"] = None
        for report in reader.root.glob("benchmark-*"):
            if not report.resolve().is_relative_to(reader.root):
                continue
            trials = reader.read(report.resolve(), "trials.json", [])
            if isinstance(trials, list):
                for row in trials:
                    if isinstance(row, dict) and row.get("run_id") == run_id:
                        data["held_out_reward"] = row.get("held_out_reward")
        data["replay_supported"] = bool(events)
        data["detailed_replay"] = bool(
            events
            and events[0].get("schema_version") == 2
            and not any("event" in w.lower() for w in warnings)
        )
        if not data["detailed_replay"]:
            warnings.append(
                "Legacy trace: some intermediate states and request durations are unavailable"
            )
        return Response(data=data, warnings=warnings)

    @app.get("/api/runs/{run_id}/tree", response_model=Envelope[SearchTreeResponse])
    def tree(run_id: str) -> Response:
        warnings: list[str] = []
        raw = reader.read(reader.directory(run_id), "tree.json", warnings)
        try:
            data = SearchTree.model_validate(raw).model_dump(mode="json") if raw else {"nodes": {}}
        except ValueError:
            warnings.append("Invalid tree")
            data = {"nodes": {}}
        return Response(data=data, warnings=warnings)

    @app.get("/api/runs/{run_id}/events", response_model=Envelope[list[SearchEventResponse]])
    def events(run_id: str, after: int = Query(0, ge=0), before: int | None = None) -> Response:
        warnings: list[str] = []
        data = reader.events(reader.directory(run_id), warnings)
        return Response(
            data=[
                e
                for e in data
                if e["sequence"] > after and (before is None or e["sequence"] <= before)
            ],
            warnings=warnings,
        )

    @app.get("/api/runs/{run_id}/timeline", response_model=Envelope[WorkerTimelineResponse])
    def activity(run_id: str) -> Response:
        warnings: list[str] = []
        return Response(
            data=timeline(reader.events(reader.directory(run_id), warnings)), warnings=warnings
        )

    @app.get("/api/runs/{run_id}/metrics", response_model=Envelope[RunMetricsResponse])
    def metrics(run_id: str) -> Response:
        summary = detail(run_id)
        nodes = list(tree(run_id).data["nodes"].values())
        trace = reader.events(reader.directory(run_id), [])
        tasks = {
            e.get("task_id"): e.get("frontier_index")
            for e in trace
            if e["event_type"] == "BRANCH_TASK_CREATED"
        }
        frontiers = []
        for event in trace:
            if event["event_type"] != "FRONTIER_COMPLETED":
                continue
            index = event.get("frontier_index")
            members = [
                e for e in trace if e.get("task_id") in tasks and tasks[e.get("task_id")] == index
            ]
            rewards = [
                e["reward"]
                for e in members
                if e["event_type"] == "CANDIDATE_EVALUATED"
                and isinstance(e.get("reward"), (int, float))
            ]
            pruning = next(
                (
                    e
                    for e in trace
                    if e["event_type"] == "FRONTIER_PRUNED" and e.get("frontier_index") == index
                ),
                None,
            )
            frontiers.append(
                {
                    "frontier": index,
                    "duration": event.get("duration_seconds"),
                    "generated": sum(e["event_type"] == "CANDIDATE_GENERATED" for e in members),
                    "evaluated": len(rewards),
                    "best_reward": max(rewards, default=None),
                    "retained": len(pruning.get("survivors", [])) if pruning else None,
                    "pruned": sum(
                        e["event_type"] == "NODE_PRUNED" and e.get("frontier_index") == index
                        for e in trace
                    )
                    if pruning
                    else None,
                }
            )
        return Response(
            data=dict(
                **summary.data.get("budget", {}),
                frontiers=frontiers,
                max_depth=max((n["depth"] for n in nodes), default=0),
                successful=sum(
                    n.get("evaluation") is not None and n["evaluation"]["reward"] == 1
                    for n in nodes
                ),
                statuses={
                    status: sum(n["status"] == status for n in nodes if n["candidate"])
                    for status in ("EVALUATED", "FAILED", "PRUNED")
                },
            ),
            warnings=summary.warnings,
        )

    return app


app = create_app()
