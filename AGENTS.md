# Repository Guidelines

## Project Structure & Module Organization

`src/branchforge/` contains the Python package: `search.py` implements policies and orchestration, `agents.py` manages workers, `llm.py` integrates providers, and `execution.py` handles Docker evaluation. Shared models, configuration, persistence, and budgets live in adjacent modules. `cli.py` exposes terminal commands.

Tests live in `tests/`. `configs/` contains fake-provider and real-provider settings. `examples/` separates visible problems, hidden tests, reference solutions, and benchmark suites. Consult `docs/prompts/001-mvp.md` for requirements and `docs/validation.md` for recorded validation. Generated `runs/` artifacts are ignored by Git.

## Build, Test, and Development Commands

- `uv sync --locked`: install dependencies from the committed lockfile.
- `docker pull python:3.12-slim`: prepare the execution image; start Docker first.
- `uv run pytest -q`: run all tests, including available Docker integrations.
- `uv run pytest -m docker -q`: run only Docker tests.
- `uv run ruff check src tests`: check lint rules.
- `uv run ruff format src tests`: format Python code.
- `uv run mypy src`: check types.
- `uv build`: build source and wheel distributions.

Run a credential-free demo with:

```sh
uv run branchforge solve --problem examples/problems/max_subarray.yaml --algorithm beam --parallel-agents 4
```

## Coding Style & Naming Conventions

Target Python 3.12+. Use four-space indentation, a 100-character line limit, `snake_case` functions/modules, and `PascalCase` classes. Use typed interfaces and Pydantic models at boundaries. Keep asynchronous work bounded and cleanup explicit. Follow Ruff formatting; CI checks formatting without rewriting files.

## Testing Guidelines

Use pytest and pytest-asyncio; name files `test_*.py` and functions `test_*`. Add regression tests for changed behavior. No numeric coverage threshold is configured. Use deterministic fake providers and synchronization primitives for concurrency tests. Never require paid API calls. Docker tests skip when prerequisites are unavailable; report skips explicitly rather than claiming full validation.

## Commit & Pull Request Guidelines

Existing commits use short imperative subjects, such as “Drain Docker output concurrently with termination.” Keep commits focused. PRs should explain the problem, resulting behavior, relevant issue links, and validation commands/results. Document limitations and configuration changes. Run the CI checks above before requesting review.

## Security & Architecture Constraints

Never execute generated code on the host or expose credentials to containers. Keep hidden tests outside search-worker inputs and artifacts. Preserve isolated branch histories, deterministic beam-frontier commits, and sequential MCTS. Store provider credentials in environment variables; never commit keys or `.env` files.
