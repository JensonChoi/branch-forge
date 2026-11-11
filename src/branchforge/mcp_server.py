"""Portable stdio tools; stdout belongs exclusively to MCP."""

import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .dashboard import Dashboard
from .service import JobService, Submission, ToolResult


def create_server(root: Path | None = None, max_active: int = 1) -> FastMCP:
    service: JobService
    dashboard: Dashboard

    @asynccontextmanager
    async def lifespan(server: FastMCP):
        nonlocal service, dashboard
        service = JobService(root, max_active)
        dashboard = Dashboard(service.root)
        try:
            yield {}
        finally:
            await service.close()
            await dashboard.close()

    server = FastMCP("BranchForge", lifespan=lifespan)
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)

    @server.tool(annotations=read)
    async def check_environment(
        provider: Literal["fake", "real"] = "fake", model: str = "openai/gpt-4o-mini"
    ) -> ToolResult:
        """Check Docker/image, provider credential presence, storage and packaged UI."""
        return await service.environment(provider, model)

    @server.tool(annotations=write)
    async def start_search(request: Submission) -> ToolResult:
        """Start a bounded Python stdin/stdout search and promptly return its run ID."""
        return await service.start(request)

    @server.tool(annotations=read)
    def get_search_status(run_id: str) -> ToolResult:
        """Read lifecycle, progress, termination reason and selected node."""
        return service.status(run_id)

    @server.tool(annotations=write)
    async def cancel_search(run_id: str) -> ToolResult:
        """Request cancellation; poll until cleanup has completed."""
        return await service.cancel(run_id)

    @server.tool(annotations=read)
    def list_runs(offset: int = 0, limit: int = 20, state: str | None = None) -> ToolResult:
        """Page saved run summaries."""
        return service.list_runs(offset, limit, state)

    @server.tool(annotations=read)
    def get_run(run_id: str) -> ToolResult:
        """Read bounded summary; fetch selected_node_id with get_candidate."""
        return service.status(run_id)

    @server.tool(annotations=read)
    def get_candidate(run_id: str, node_id: str, offset: int = 0, limit: int = 8000) -> ToolResult:
        """Read paginated JSON containing code, ancestry and visible feedback."""
        return service.candidate(run_id, node_id, offset, limit)

    @server.tool(annotations=read)
    def compare_runs(run_ids: list[str]) -> ToolResult:
        """Compare up to ten summaries; differences can invalidate reward comparisons."""
        if not 2 <= len(run_ids) <= 10:
            raise ValueError("INVALID_INPUT: supply 2..10 run IDs")
        rows = []
        for run_id in run_ids:
            row = service.status(run_id).data
            warnings: list[str] = []
            directory = service.reader.directory(run_id)
            problem = service.reader.read(directory, "problem.json", warnings)
            row["problem_fingerprint"] = hashlib.sha256(
                json.dumps(problem, sort_keys=True).encode()
            ).hexdigest()
            config = service.reader.read(directory, "config.json", warnings)
            row["provider"] = config.get("llm", {}).get("provider")
            row["limits"] = config.get("budget", {})
            rows.append(row)
        return ToolResult(
            data={"runs": rows},
            warnings=["Compare tests, provider, model and limits before rewards."],
        )

    @server.tool(annotations=write)
    async def get_dashboard_url(run_id: str | None = None) -> ToolResult:
        """Start/reuse this server's loopback dashboard, without launching a browser."""
        if run_id:
            service.reader.directory(run_id)
        url = await dashboard.start()
        return ToolResult(data={"url": url + (f"/runs/{run_id}" if run_id else "/")})

    return server
