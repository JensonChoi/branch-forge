"""Pinned LiveCodeBench JSONL adapter; never unpickle dataset values on the host."""

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from pydantic import Field

from ..models import Frozen, TestCase, VisibleProblem

DATASET_REVISION = "0fe84c3912ea0c4d4a78037083943e8f0c4dd505"
GRADER_REVISION = "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"
RELEASE = "release_v6"
FILES = ["test.jsonl"] + [f"test{i}.jsonl" for i in range(2, 7)]


class Problem(Frozen):
    question_id: str
    title: str
    statement: str
    platform: str
    difficulty: str
    contest_date: str
    starter_code: str = ""
    function_name: str | None = None
    public_tests: tuple[TestCase, ...] = Field(min_length=1)

    def visible(self) -> VisibleProblem:
        return VisibleProblem(
            problem_id=self.question_id,
            title=self.title,
            statement=self.statement + "\nStarter code:\n" + self.starter_code,
            input_format=(
                f"Implement Solution.{self.function_name}" if self.function_name else "stdin"
            ),
            output_format="Return the required value" if self.function_name else "stdout",
            visible_tests=self.public_tests,
            time_limit_seconds=6,
            memory_limit_mb=512,
        )


def parse_public(row: dict[str, Any]) -> Problem:
    tests = json.loads(row["public_test_cases"])
    metadata = json.loads(row["metadata"])
    function = metadata.get("func_name")
    if any(t["testtype"] != ("functional" if function else "stdin") for t in tests):
        raise ValueError("Test convention and func_name disagree")
    return Problem(
        question_id=str(row["question_id"]),
        title=row["question_title"],
        statement=row["question_content"],
        platform=row["platform"],
        difficulty=row["difficulty"],
        contest_date=row["contest_date"],
        starter_code=row["starter_code"],
        function_name=function,
        public_tests=tuple(TestCase(input=t["input"], expected_output=t["output"]) for t in tests),
    )


def download(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = cache / name
        if target.exists():
            continue
        url = (
            "https://huggingface.co/datasets/livecodebench/code_generation_lite/resolve/"
            f"{DATASET_REVISION}/{name}"
        )
        temporary = target.with_suffix(".partial")
        with urlopen(url, timeout=120) as source, temporary.open("wb") as stream:
            while chunk := source.read(1024 * 1024):
                stream.write(chunk)
        temporary.replace(target)


def load_public(cache: Path) -> tuple[list[Problem], dict[str, str], list[dict[str, str]]]:
    problems: dict[str, Problem] = {}
    hashes = {}
    exclusions = []
    for name in FILES:
        digest = hashlib.sha256()
        with (cache / name).open("rb") as stream:
            for line in stream:
                digest.update(line)
                row = json.loads(line)
                if not json.loads(row["public_test_cases"]):
                    exclusions.append(
                        {"question_id": str(row["question_id"]), "reason": "no public tests"}
                    )
                    continue
                problem = parse_public(row)
                if problem.question_id in problems:
                    raise ValueError(f"Duplicate question ID: {problem.question_id}")
                problems[problem.question_id] = problem
        hashes[name] = digest.hexdigest()
    return list(problems.values()), hashes, exclusions


def select(problems: list[Problem], size: int, seed: int) -> list[Problem]:
    if size < 1 or size > len(problems):
        raise ValueError("Sample size exceeds eligible population")
    # Equal allocation across joint strata, redistributed when small strata exhaust.
    strata: dict[tuple[str, str, str], list[Problem]] = defaultdict(list)
    for p in sorted(problems, key=lambda p: p.question_id):
        strata[p.difficulty, p.platform, p.contest_date[:7]].append(p)
    rng = random.Random(seed)
    keys = sorted(strata)
    rng.shuffle(keys)
    for group in strata.values():
        rng.shuffle(group)
    result: list[Problem] = []
    while len(result) < size:
        for key in keys:
            if strata[key] and len(result) < size:
                result.append(strata[key].pop())
    return result


def private_row(cache: Path, question_id: str) -> dict[str, Any]:
    """Called only by final grading, after selection is frozen."""
    for name in FILES:
        with (cache / name).open() as stream:
            for line in stream:
                row = json.loads(line)
                if str(row["question_id"]) == question_id:
                    return row
    raise ValueError("Selected problem missing from pinned cache")
