"""Process-owned local jobs. No host commands or hidden tests cross this boundary."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from filelock import FileLock, Timeout
from pydantic import Field

from .api.app import Reader
from .config import Config, Settings
from .execution import DockerExecutor
from .models import VisibleProblem
from .search import SearchOrchestrator


def data_root() -> Path:
    return Path(os.environ.get("BRANCHFORGE_DATA_DIR", "~/.local/share/branchforge")).expanduser()


class Submission(Settings):
    problem: VisibleProblem
    provider: Literal["fake", "real"]
    model: str = Field(default="openai/gpt-4o-mini", min_length=1, max_length=200)
    algorithm: Literal["baseline", "best_of_n", "beam", "mcts"] = "beam"
    max_llm_calls: int = Field(default=10, ge=1, le=10000)
    max_candidates: int = Field(default=10, ge=1, le=10000)
    timeout_seconds: float = Field(default=300, gt=0, le=86400)
    concurrency: int = Field(default=4, ge=1, le=32)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    def config(self, root: Path) -> Config:
        cfg = Config(runs_dir=root)
        cfg.llm.provider = self.provider
        cfg.llm.model = self.model
        cfg.budget.max_tokens = None
        cfg.budget.max_llm_calls = self.max_llm_calls
        cfg.budget.max_candidates = self.max_candidates
        cfg.budget.max_wall_time_seconds = self.timeout_seconds
        cfg.agents.max_concurrent = (
            1 if self.algorithm in {"baseline", "mcts"} else self.concurrency
        )
        cfg.llm.max_concurrent_requests = cfg.agents.max_concurrent
        cfg.execution.max_concurrent_containers = cfg.agents.max_concurrent
        if len(self.problem.model_dump_json()) > 12000:
            raise ValueError("INVALID_INPUT: problem exceeds 12000 characters")
        return cfg


class ToolResult(Settings):
    data: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


def credentials(model: str) -> bool | None:
    keys = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "azure": "AZURE_API_KEY",
    }
    key = keys.get(model.split("/")[0])
    return bool(os.environ.get(key)) if key else None


def create_search(problem: VisibleProblem, config: Config, algorithm: str) -> SearchOrchestrator:
    """Shared CLI/service construction; reject unsupported guarantees before creating artifacts."""
    if config.budget.max_cost_usd is not None:
        raise ValueError("Hard cost limits are unsupported")
    if config.llm.provider != "fake" and config.budget.max_tokens is not None:
        raise ValueError("Hard token limits are unsupported for real providers")
    return SearchOrchestrator(problem, config, algorithm)


class JobService:
    def __init__(self, root: Path | None = None, max_active: int = 1):
        if not 1 <= max_active <= 32:
            raise ValueError("max_active must be 1..32")
        self.root = (root or data_root()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.reader = Reader(self.root)
        self.owner = uuid4().hex
        self.lock = FileLock(self.root / f".owner-{self.owner}.lock")
        self.lock.acquire()
        self.max_active = max_active
        self.tasks: dict[str, asyncio.Task] = {}
        self.engines: dict[str, SearchOrchestrator] = {}
        self.admission = asyncio.Lock()
        self.closed = False

    def metadata(self, run_id: str) -> dict:
        warnings: list[str] = []
        value = self.reader.read(self.reader.directory(run_id), "job.json", warnings)
        return value if isinstance(value, dict) else {}

    def save(self, run_id: str, meta: dict) -> None:
        directory = self.reader.directory(run_id)
        target = directory / "job.json"
        temporary = directory / f"job-{self.owner}.tmp"
        temporary.write_text(json.dumps(meta))
        temporary.replace(target)

    async def environment(
        self, provider: str = "fake", model: str = "openai/gpt-4o-mini"
    ) -> ToolResult:
        from importlib.metadata import version
        from importlib.resources import files

        ready = True
        try:
            await DockerExecutor(Config().execution).check()
        except (OSError, RuntimeError, TimeoutError):
            ready = False
        return ToolResult(
            data={
                "version": version("branchforge"),
                "demo_problem": json.loads(
                    files("branchforge").joinpath("resources/demo.json").read_text()
                ),
                "docker_and_image_ready": ready,
                "provider": provider,
                "model": model,
                "credential_present": credentials(model) if provider == "real" else None,
                "data_directory_writable": os.access(self.root, os.W_OK),
                "dashboard_available": files("branchforge").joinpath("web/index.html").is_file(),
            },
            warnings=[] if ready else ["Start Docker and pull python:3.12-slim."],
        )

    async def start(self, request: Submission) -> ToolResult:
        cfg = request.config(self.root)
        fingerprint = hashlib.sha256(
            request.model_dump_json(exclude={"idempotency_key"}).encode()
        ).hexdigest()
        async with self.admission:
            # Short synchronous cross-process critical section; never await while holding it.
            with FileLock(self.root / ".admission.lock", timeout=2):
                if request.idempotency_key:
                    for directory in self.root.iterdir():
                        if not directory.is_dir() or directory.is_symlink():
                            continue
                        meta = self.metadata(directory.name)
                        if meta.get("idempotency_key") == request.idempotency_key:
                            if meta.get("fingerprint") != fingerprint:
                                raise ValueError("IDEMPOTENCY_CONFLICT")
                            return self.status(directory.name)
                if self.closed or sum(not t.done() for t in self.tasks.values()) >= self.max_active:
                    raise ValueError("ADMISSION_LIMIT: server is closed or busy")
                if request.provider == "real" and credentials(request.model) is False:
                    raise ValueError("MISSING_CREDENTIALS: configure provider environment")
                engine = create_search(request.problem, cfg, request.algorithm)
                run_id = engine.run_id
                self.engines[run_id] = engine
                engine.events.save("config.json", cfg.model_dump(mode="json"))
                engine.events.save("problem.json", request.problem.model_dump(mode="json"))
                engine.snapshot()
                self.save(
                    run_id,
                    {
                        "owner": self.owner,
                        "state": "running",
                        "fingerprint": fingerprint,
                        "idempotency_key": request.idempotency_key,
                    },
                )
                self.tasks[run_id] = asyncio.create_task(self._run(engine))
            return self.status(run_id)

    async def _run(self, engine: SearchOrchestrator) -> None:
        meta = self.metadata(engine.run_id)
        try:
            result = await engine.run()
            reason = result["termination_reason"]
            meta["state"] = (
                "canceled"
                if reason == "USER_CANCELED"
                else "failed"
                if reason == "ERROR"
                else "completed"
            )
        except asyncio.CancelledError:
            meta["state"] = "canceled"
        except Exception:  # noqa: BLE001 -- persist failure without leaking provider secrets
            meta["state"] = "failed"
        finally:
            self.save(engine.run_id, meta)
            self.engines.pop(engine.run_id, None)

    def status(self, run_id: str) -> ToolResult:
        directory = self.reader.directory(run_id)
        meta = self.metadata(run_id)
        state = meta.get("state", "interrupted")
        owner = meta.get("owner")
        if state in {"running", "cancel_requested"} and owner != self.owner:
            if not isinstance(owner, str) or not owner.isalnum():
                state = "interrupted"
            else:
                try:
                    with FileLock(self.root / f".owner-{owner}.lock", timeout=0):
                        state = "interrupted"
                except Timeout:
                    pass
        warnings: list[str] = []
        summary = self.reader.summary(directory, warnings)
        if not meta:
            state = summary["status"] if summary["termination_reason"] else "interrupted"
        engine = self.engines.get(run_id)
        config = self.reader.read(directory, "config.json", warnings)
        summary.update(
            state=state,
            owned=owner == self.owner,
            provider=(config.get("llm") or {}).get("provider"),
        )
        if engine:
            summary["budget"] = engine.budget.summary()
        for key, value in summary.items():
            if isinstance(value, str) and len(value) > 512:
                summary[key] = value[:512]
                warnings.append(f"{key} truncated")
        return ToolResult(data=summary, warnings=warnings)

    async def cancel(self, run_id: str) -> ToolResult:
        result = self.status(run_id)
        if result.data["state"] not in {"running", "cancel_requested"}:
            return result
        if not result.data["owned"]:
            raise ValueError("OWNERSHIP_CONFLICT: cancel through the owning server")
        task = self.tasks[run_id]
        if result.data["state"] != "cancel_requested":
            meta = self.metadata(run_id)
            meta["state"] = "cancel_requested"
            self.save(run_id, meta)
            # Let the coroutine enter its cleanup scope before cancellation.
            await asyncio.sleep(0)
            if not task.done():
                task.cancel()
        return self.status(run_id)

    def list_runs(self, offset: int = 0, limit: int = 20, state: str | None = None) -> ToolResult:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("INVALID_INPUT: pagination")
        ids = sorted(p.name for p in self.root.iterdir() if p.is_dir() and not p.is_symlink())
        if state:
            ids = [i for i in ids if self.status(i).data["state"] == state]
        return ToolResult(
            data={
                "runs": [self.status(i).data for i in ids[offset : offset + limit]],
                "total": len(ids),
            }
        )

    def candidate(
        self, run_id: str, node_id: str, offset: int = 0, limit: int = 8000
    ) -> ToolResult:
        if offset < 0 or not 1 <= limit <= 16000:
            raise ValueError("INVALID_INPUT: pagination")
        warnings: list[str] = []
        tree = self.reader.read(self.reader.directory(run_id), "tree.json", warnings)
        node = tree.get("nodes", {}).get(node_id)
        if not node:
            raise ValueError("ARTIFACT_UNAVAILABLE: candidate node")
        payload = json.dumps(node)
        return ToolResult(
            data={
                "node_id": node_id,
                "offset": offset,
                "text": payload[offset : offset + limit],
                "total_chars": len(payload),
                "truncated": offset + limit < len(payload),
            },
            warnings=warnings,
        )

    async def close(self) -> None:
        self.closed = True
        for run_id in self.tasks:
            await self.cancel(run_id)
        if self.tasks:
            await asyncio.wait(list(self.tasks.values()), timeout=30)
        self.lock.release()
