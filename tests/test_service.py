import asyncio
import json
import sys
from importlib.resources import files

import pytest
from fastapi import HTTPException
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from branchforge.search import SearchOrchestrator
from branchforge.service import JobService, Submission


def request(**kwargs):
    return Submission.model_validate(
        dict(
            problem=json.loads(files("branchforge").joinpath("resources/demo.json").read_text()),
            provider="fake",
            **kwargs,
        )
    )


async def test_admission_retry_cancel_and_ownership(tmp_path, monkeypatch):
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    async def run(self):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(SearchOrchestrator, "run", run)
    service = JobService(tmp_path)
    other = JobService(tmp_path)
    try:
        first = await service.start(request(idempotency_key="retry"))
        run_id = first.data["run_id"]
        assert (await other.start(request(idempotency_key="retry"))).data["run_id"] == run_id
        with pytest.raises(ValueError, match="IDEMPOTENCY"):
            await service.start(request(idempotency_key="retry", max_llm_calls=2))
        with pytest.raises(ValueError, match="ADMISSION"):
            await service.start(request())
        with pytest.raises(ValueError, match="OWNERSHIP"):
            await other.cancel(run_id)
        await entered.wait()
        assert (await service.cancel(run_id)).data["state"] == "cancel_requested"
        await service.tasks[run_id]
        assert cleaned.is_set()
        assert (await service.cancel(run_id)).data["state"] == "canceled"
    finally:
        await service.close()
        await other.close()


async def test_restart_and_unsafe_artifacts(tmp_path):
    service = JobService(tmp_path)
    directory = tmp_path / "abandoned"
    directory.mkdir()
    service.save("abandoned", {"owner": "deadbeef", "state": "running"})
    assert service.status("abandoned").data["state"] == "interrupted"
    with pytest.raises(HTTPException):
        service.status("../escape")
    await service.close()


async def test_stdio_discovery_validation_and_listing(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            (
                "from branchforge.mcp_server import create_server; from pathlib import Path; "
                f"create_server(Path({str(tmp_path)!r})).run()"
            ),
        ],
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
        await client.initialize()
        tools = await client.list_tools()
        assert len(tools.tools) == 9
        result = await client.call_tool("list_runs", {})
        assert not result.isError
        assert result.structuredContent["data"]["runs"] == []
        invalid = await client.call_tool("start_search", {"request": {"provider": "fake"}})
        assert invalid.isError
        unknown = await client.call_tool("get_run", {"run_id": "missing"})
        assert unknown.isError


async def test_cancel_immediately_and_shutdown(tmp_path, monkeypatch):
    entered = asyncio.Event()

    async def run(self):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(SearchOrchestrator, "run", run)
    service = JobService(tmp_path)
    result = await service.start(request())
    await service.close()
    assert entered.is_set()
    assert service.status(result.data["run_id"]).data["state"] == "canceled"


async def test_dashboard_deeplink_and_port_conflict(tmp_path):
    import socket

    import httpx

    from branchforge.dashboard import Dashboard

    occupied = socket.socket()
    try:
        occupied.bind(("127.0.0.1", 0))
    except PermissionError:
        occupied.close()
        pytest.skip("sandbox denies loopback binding")
    occupied.listen()
    ui = Dashboard(tmp_path)
    try:
        url = await ui.start(occupied.getsockname()[1])
        assert not url.endswith(":" + str(occupied.getsockname()[1]))
        assert await ui.start() == url
        async with httpx.AsyncClient() as client:
            assert (await client.get(url + "/runs/example")).status_code == 200
            assert (await client.get(url + "/api/health")).json()["status"] == "ok"
            assert (await client.post(url + "/api/runs")).status_code == 405
    finally:
        await ui.close()
        occupied.close()


@pytest.mark.docker
async def test_stdio_fake_search_cancel_and_reopen(tmp_path):
    from branchforge.config import ExecutionConfig
    from branchforge.execution import DockerExecutor

    try:
        await DockerExecutor(ExecutionConfig()).check()
    except (OSError, RuntimeError, TimeoutError) as exc:
        pytest.skip(str(exc))
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            f"from pathlib import Path; from branchforge.mcp_server import create_server; create_server(Path({str(tmp_path)!r})).run()",
        ],
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
        await client.initialize()
        result = await client.call_tool(
            "start_search", {"request": request().model_dump(mode="json")}
        )
        assert not result.isError
        run_id = result.structuredContent["data"]["run_id"]
        await client.call_tool("cancel_search", {"run_id": run_id})
        async with asyncio.timeout(30):
            while True:
                status = await client.call_tool("get_search_status", {"run_id": run_id})
                if status.structuredContent["data"]["state"] == "canceled":
                    break
                await asyncio.sleep(0.02)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
        await client.initialize()
        result = await client.call_tool("get_run", {"run_id": run_id})
        assert result.structuredContent["data"]["state"] == "canceled"


async def test_provider_exception_secrets_not_persisted(tmp_path):
    from branchforge.execution import Evaluator

    class FailingProvider:
        async def generate(self, messages, config):
            raise RuntimeError("secret-provider-token-should-never-be-persisted")

    class UnusedExecutor:
        async def run(self, code, stdin, problem):
            raise AssertionError("generation failed; no evaluation expected")

    submission = request()
    config = submission.config(tmp_path)
    config.llm.provider = "real"
    config.llm.retries = 0
    engine = SearchOrchestrator(
        submission.problem, config, "baseline", FailingProvider(), Evaluator(UnusedExecutor())
    )
    await engine.run()
    for artifact in (tmp_path / engine.run_id).iterdir():
        assert "secret-provider-token" not in artifact.read_text()
