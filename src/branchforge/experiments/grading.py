"""Official checker in the existing credential-free Docker sandbox."""

import json
import time

from pydantic import BaseModel

from ..execution import DockerExecutor, Evaluator
from ..models import Candidate, EvaluationResult, TestResult, TestStatus, VisibleProblem

# This script runs inside Docker, including decompression/deserialization of private data.
DRIVER = """
import sys, json, base64, zlib, pickle
sys.path.insert(0, "/opt/lcb")
from lcb_runner.evaluation.compute_code_generation_metrics import evaluate_generations_by_problem
payload = json.loads(sys.stdin.read())
tests = payload["public"]
if payload.get("private") is not None:
    raw = payload["private"]
    try:
        private = json.loads(raw)
    except ValueError:
        private = json.loads(pickle.loads(zlib.decompress(base64.b64decode(raw))))
    tests += private
sample = {"input_output": json.dumps({
    "inputs": [t["input"] for t in tests], "outputs": [t["output"] for t in tests],
    "fn_name": payload["function"]})}
results, metadata = evaluate_generations_by_problem(([payload["code"]], sample, False, 6))
# Private diagnostic contents must never leave this container.
flags = [bool(x > 0) for x in results[0]]
error_code = metadata[0].get("error_code")
print("BRANCHFORGE_GRADE=" + json.dumps({"passed": bool(flags) and all(flags),
    "flags": flags if payload.get("private") is None else [],
    "error_code": error_code}))
"""


class Grade(BaseModel):
    passed: bool | None = None
    status: str
    error_code: int | None = None
    flags: list[bool] = []


class OfficialGrader:
    def __init__(self, executor: DockerExecutor):
        self.executor = executor

    async def grade(
        self, code: str, problem: VisibleProblem, function: str | None, private: str | None = None
    ) -> Grade:
        public = [{"input": t.input, "output": t.expected_output} for t in problem.visible_tests]
        payload = json.dumps(
            {"code": code, "public": public, "private": private, "function": function}
        )
        sandbox = problem.model_copy(update={"time_limit_seconds": 600 if private else 90})
        stdout, _, rc, status = await self.executor.run(DRIVER, payload, sandbox)
        if status or rc:
            return Grade(status=status or "GRADER_ERROR")
        try:
            raw = json.loads(stdout.rsplit("BRANCHFORGE_GRADE=", 1)[1].strip())
            if raw.get("error_code") == -5:
                return Grade(status="GRADER_ERROR", error_code=-5)
            return Grade(status="PASS" if raw["passed"] else "FAIL", **raw)
        except (ValueError, IndexError, KeyError):
            return Grade(status="GRADER_ERROR")


class PublicEvaluator(Evaluator):
    """Public-only official semantics for both submission conventions."""

    def __init__(self, grader: OfficialGrader, function: str | None):
        self.grader, self.function = grader, function
        self.executor = grader.executor

    async def evaluate(self, candidate: Candidate, problem: VisibleProblem) -> EvaluationResult:
        started = time.monotonic()
        grade = await self.grader.grade(candidate.code, problem, self.function)
        flags = grade.flags
        infrastructure = grade.passed is None
        passed = sum(flags)
        return EvaluationResult(
            candidate_id=candidate.candidate_id,
            passed_tests=passed,
            total_tests=len(problem.visible_tests),
            reward=None if infrastructure else passed / len(problem.visible_tests),
            execution_time_ms=(time.monotonic() - started) * 1000,
            error=grade.status if infrastructure else None,
            test_results=tuple(
                TestResult(
                    test_id=str(i),
                    status=TestStatus.PASS if flag else TestStatus.WRONG_ANSWER,
                    expected_output=problem.visible_tests[i].expected_output,
                )
                for i, flag in enumerate(flags[: len(problem.visible_tests)])
            ),
        )
