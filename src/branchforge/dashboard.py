"""Owned loopback dashboard with an atomically reserved port."""

import asyncio
import socket
from importlib.resources import files
from pathlib import Path

import uvicorn
from fastapi import HTTPException
from fastapi.responses import FileResponse

from .api.app import create_app


class Dashboard:
    def __init__(self, root: Path):
        self.root = root
        self.task: asyncio.Task | None = None
        self.server: uvicorn.Server | None = None
        self.socket: socket.socket | None = None
        self.url = ""

    async def start(self, port: int = 0) -> str:
        if self.task and not self.task.done():
            return self.url
        web = Path(str(files("branchforge").joinpath("web"))).resolve()
        if not (web / "index.html").is_file():
            raise ValueError("DASHBOARD_UNAVAILABLE: install a prepared distribution")
        app = create_app(self.root)

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            target = (web / path).resolve()
            if not target.is_relative_to(web) or path.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(target if target.is_file() else web / "index.html")

        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        self.socket = sock
        self.url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        self.task = asyncio.create_task(self.server.serve(sockets=[sock]))
        for _ in range(100):
            if self.server.started:
                return self.url
            if self.task.done():
                await self.task
                raise RuntimeError("Dashboard failed to start")
            await asyncio.sleep(0.02)
        await self.close()
        raise RuntimeError("Dashboard startup timed out")

    async def close(self) -> None:
        if self.server:
            self.server.should_exit = True
        if self.task:
            await self.task
        if self.socket:
            self.socket.close()
