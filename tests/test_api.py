import json
from pathlib import Path

from fastapi.testclient import TestClient

from branchforge.api.app import create_app, timeline


def test_partial_and_traversal(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/runs").json()["data"]["total"] == 1
    response = client.get("/api/runs/run").json()
    assert response["data"]["status"] == "partial"
    assert response["warnings"]
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/runs/a.b").status_code == 400
    (tmp_path / "escape").symlink_to(tmp_path.parent)
    assert client.get("/api/runs/escape").status_code == 404


def test_events_and_unsafe_artifact(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    directory.mkdir()
    events = [
        {"sequence": 3, "event_type": "UNKNOWN"},
        {"sequence": 1, "event_type": "RUN_STARTED"},
    ]
    (directory / "events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\ninvalid\n")
    (directory / "config.json").symlink_to(tmp_path.parent / "secret")
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/runs/run/events").json()
    assert [e["sequence"] for e in response["data"]] == [1, 3]
    assert len(response["warnings"]) == 2
    assert len(client.get("/api/runs/run/events?after=1").json()["data"]) == 1
    assert "unsafe path" in str(client.get("/api/runs/run").json()["warnings"])


def test_timeline_overlap_and_worker_reuse() -> None:
    def event(kind: str, task: str, second: int) -> dict:
        return {
            "event_type": kind,
            "task_id": task,
            "worker_id": "slot",
            "timestamp": f"2026-01-01T00:00:{second:02d}+00:00",
        }

    result = timeline(
        [
            event("SUBAGENT_STARTED", "a", 0),
            event("SUBAGENT_STARTED", "b", 1),
            event("SUBAGENT_FINISHED", "a", 3),
            event("SUBAGENT_FINISHED", "b", 4),
            event("SUBAGENT_STARTED", "c", 5),
        ]
    )
    assert result["peak_concurrency"] == 2
    assert result["busy_seconds"] == 6
    assert result["intervals"][-1]["end"] is None
