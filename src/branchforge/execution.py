import asyncio
import hashlib
import json
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .config import ExecutionConfig
from .models import Candidate, EvaluationResult, TestResult, TestStatus, VisibleProblem
from .runtime import Limiter


def normalize(text: str) -> str:
    return "\n".join(
        line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).rstrip()


class Executor(Protocol):
    async def run(
        self, code: str, stdin: str, problem: VisibleProblem
    ) -> tuple[str, str, int | None, str | None]: ...


class DockerExecutor:
    def __init__(self, config: ExecutionConfig):
        self.config = config
        self.limiter = Limiter(config.max_concurrent_containers)
        self.containers: set[str] = set()

    async def command(self, *args: str) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            async with asyncio.timeout(20):
                out, err = await process.communicate()
            return (
                process.returncode or 0,
                out.decode(errors="replace"),
                err.decode(errors="replace"),
            )
        finally:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.communicate()

    async def check(self) -> None:
        code, _, error = await self.command("info", "--format", "{{.ServerVersion}}")
        if code:
            raise RuntimeError("Docker unavailable: " + error)
        code, _, error = await self.command("image", "inspect", self.config.image)
        if code:
            raise RuntimeError(
                f"Execution image unavailable; run docker pull {self.config.image}: {error}"
            )

    async def run(
        self, code: str, stdin: str, problem: VisibleProblem
    ) -> tuple[str, str, int | None, str | None]:
        async with self.limiter:
            name = "branchforge-" + uuid4().hex
            self.containers.add(name)
            try:
                with tempfile.TemporaryDirectory(prefix="branchforge-") as directory:
                    source = Path(directory) / "solution.py"
                    source.write_text(code)
                    source.chmod(0o444)
                    rc, _, err = await self.command(
                        "create",
                        "--name",
                        name,
                        "--network",
                        "none",
                        "--user",
                        "65534:65534",
                        "--cap-drop",
                        "ALL",
                        "--security-opt",
                        "no-new-privileges",
                        "--read-only",
                        "--memory",
                        f"{problem.memory_limit_mb}m",
                        "--memory-swap",
                        f"{problem.memory_limit_mb}m",
                        "--cpus",
                        str(self.config.cpus),
                        "--pids-limit",
                        str(self.config.pids_limit),
                        "--tmpfs",
                        "/tmp:rw,noexec,nosuid,size=16m",
                        "--mount",
                        f"type=bind,src={source},dst=/solution.py,readonly",
                        "--log-driver",
                        "none",
                        "-i",
                        self.config.image,
                        "python",
                        "-I",
                        "-B",
                        "/solution.py",
                    )
                    if rc:
                        return "", err, None, "INFRASTRUCTURE_ERROR"
                    process = await asyncio.create_subprocess_exec(
                        "docker",
                        "start",
                        "-ai",
                        name,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    buffers = [bytearray(), bytearray()]
                    overflow = False

                    async def read(stream: asyncio.StreamReader, index: int) -> None:
                        nonlocal overflow
                        while chunk := await stream.read(4096):
                            remaining = self.config.output_limit_bytes - len(buffers[index])
                            buffers[index].extend(chunk[:remaining])
                            if len(chunk) > remaining and not overflow:
                                overflow = True
                                # Docker may wait for its attach stream to drain before kill
                                # completes. Keep both readers running while termination runs.
                                group.create_task(self.command("kill", name))

                    async def feed() -> None:
                        assert process.stdin
                        try:
                            process.stdin.write(stdin.encode())
                            await process.stdin.drain()
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        finally:
                            process.stdin.close()

                    status = None
                    try:
                        async with asyncio.timeout(problem.time_limit_seconds):
                            async with asyncio.TaskGroup() as group:
                                assert process.stdout and process.stderr
                                group.create_task(read(process.stdout, 0))
                                group.create_task(read(process.stderr, 1))
                                group.create_task(feed())
                                await process.wait()
                    except TimeoutError:
                        status = "TIME_LIMIT_EXCEEDED"
                    finally:
                        if process.returncode is None:
                            with suppress(ProcessLookupError):
                                process.kill()
                            await process.communicate()
                            await self.command("kill", name)
                    rc, state, err = await self.command(
                        "inspect", "--format", "{{json .State}}", name
                    )
                    if rc:
                        status = "INFRASTRUCTURE_ERROR"
                        exit_code = None
                    else:
                        details = json.loads(state)
                        exit_code = details["ExitCode"]
                        if details.get("OOMKilled"):
                            status = "MEMORY_LIMIT_EXCEEDED"
                    if overflow:
                        status = "RUNTIME_ERROR"
                    return (
                        buffers[0].decode(errors="replace"),
                        buffers[1].decode(errors="replace"),
                        exit_code,
                        status,
                    )
            except (OSError, TimeoutError) as exc:
                return "", str(exc), None, "INFRASTRUCTURE_ERROR"
            finally:
                try:
                    await self.command("rm", "-f", name)
                finally:
                    self.containers.discard(name)


class Evaluator:
    def __init__(self, executor: Executor):
        self.executor = executor
        self.cache: dict[str, EvaluationResult] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.executions = 0

    async def evaluate(self, candidate: Candidate, problem: VisibleProblem) -> EvaluationResult:
        # Preserve indentation and whitespace inside string literals.
        code = candidate.code.replace("\r\n", "\n")
        key = hashlib.sha256((code + problem.model_dump_json()).encode()).hexdigest()
        async with self.locks.setdefault(key, asyncio.Lock()):
            if key in self.cache:
                return self.cache[key].model_copy(update={"candidate_id": candidate.candidate_id})
            results = []
            for index, test in enumerate(problem.visible_tests):
                started = time.monotonic()
                stdout, stderr, exit_code, status = await self.executor.run(
                    code, test.input, problem
                )
                self.executions += 1
                if status is None:
                    status = (
                        "RUNTIME_ERROR"
                        if exit_code != 0
                        else "PASS"
                        if normalize(stdout) == normalize(test.expected_output)
                        else "WRONG_ANSWER"
                    )
                results.append(
                    TestResult(
                        test_id=str(index),
                        status=TestStatus(status),
                        expected_output=test.expected_output,
                        actual_output=stdout,
                        stderr=stderr,
                        exit_code=exit_code,
                        execution_time_ms=(time.monotonic() - started) * 1000,
                        error=stderr if status == "INFRASTRUCTURE_ERROR" else None,
                    )
                )
            passed = sum(r.status == TestStatus.PASS for r in results)
            infrastructure = any(r.status == TestStatus.INFRASTRUCTURE_ERROR for r in results)
            evaluation = EvaluationResult(
                candidate_id=candidate.candidate_id,
                passed_tests=passed,
                total_tests=len(results),
                reward=None if infrastructure else passed / len(results),
                test_results=tuple(results),
                execution_time_ms=sum(r.execution_time_ms for r in results),
                error="Sandbox infrastructure failure" if infrastructure else None,
            )
            if not infrastructure:
                self.cache[key] = evaluation
            return evaluation
