from pathlib import Path

import pytest
import yaml

from branchforge.config import ExecutionConfig
from branchforge.execution import DockerExecutor, Evaluator
from branchforge.models import Candidate, CodingProblem

pytestmark = pytest.mark.docker


@pytest.fixture
async def executor():
    executor = DockerExecutor(ExecutionConfig())
    try:
        await executor.check()
    except (OSError, RuntimeError, TimeoutError) as exc:
        pytest.skip(str(exc))
    return executor


@pytest.mark.parametrize(
    "name", ["max_subarray", "balanced_parentheses", "two_sum", "shortest_path", "coin_change"]
)
async def test_reference_solutions(executor, name):
    problem = CodingProblem.model_validate(
        yaml.safe_load(Path(f"examples/problems/{name}.yaml").read_text())
    ).visible()
    hidden = yaml.safe_load(Path(f"examples/hidden/{name}.yaml").read_text())
    problem = type(problem).model_validate(
        {**problem.model_dump(), "visible_tests": list(problem.visible_tests) + hidden}
    )
    candidate = Candidate(
        explanation="reference", code=Path(f"examples/references/{name}.py").read_text()
    )
    assert (await Evaluator(executor).evaluate(candidate, problem)).reward == 1
    assert not executor.containers


@pytest.mark.parametrize(
    "code,status",
    [
        ("print(0)", "WRONG_ANSWER"),
        ("invalid syntax !", "RUNTIME_ERROR"),
        ("raise Exception('oops')", "RUNTIME_ERROR"),
        ("while True: pass", "TIME_LIMIT_EXCEEDED"),
        ("a=bytearray(2**30)", "MEMORY_LIMIT_EXCEEDED"),
    ],
)
async def test_failures(executor, code, status):
    problem = CodingProblem.model_validate(
        yaml.safe_load(Path("examples/problems/max_subarray.yaml").read_text())
    ).visible()
    result = await Evaluator(executor).evaluate(Candidate(explanation="", code=code), problem)
    assert result.test_results[0].status == status
    assert not executor.containers


async def test_output_limit_and_isolation(executor):
    problem = CodingProblem.model_validate(
        yaml.safe_load(Path("examples/problems/max_subarray.yaml").read_text())
    ).visible()
    out, _, _, status = await executor.run("while True: print('x'*10000)", "", problem)
    assert len(out.encode()) <= executor.config.output_limit_bytes
    assert status in {"RUNTIME_ERROR", "TIME_LIMIT_EXCEEDED"}
    code = "import os,socket\nassert os.getuid()!=0\nassert 'OPENAI_API_KEY' not in os.environ\nassert not os.path.exists('/var/run/docker.sock')\ntry:\n open('/forbidden','w')\nexcept OSError:\n print('isolated')\n"
    out, err, exit_code, status = await executor.run(code, "", problem)
    assert out.strip() == "isolated", err
    assert exit_code == 0
    assert status is None
    assert not executor.containers


async def test_container_cancellation(executor):
    import asyncio

    problem = CodingProblem.model_validate(
        yaml.safe_load(Path("examples/problems/max_subarray.yaml").read_text())
    ).visible()
    task = asyncio.create_task(executor.run("while True: pass", "", problem))
    # Wait for a container to be running, rather than assuming startup latency.
    async with asyncio.timeout(10):
        while True:
            if executor.containers:
                name = next(iter(executor.containers))
                rc, state, _ = await executor.command(
                    "inspect", "--format", "{{.State.Running}}", name
                )
                if rc == 0 and state.strip() == "true":
                    break
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not executor.containers
    assert executor.limiter.active == 0
    rc, _, _ = await executor.command("inspect", name)
    assert rc != 0
