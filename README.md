# BranchForge

BranchForge is a local Python harness for exploring candidate solutions with explicit trees, objective visible-test feedback, and bounded inference budgets. It supports single-trajectory refinement, independent best-of-N sampling, synchronized sequential/parallel beam search, and sequential UCT MCTS.

Search improving reliability is an experimental question. Included fake-provider fixtures demonstrate runtime behavior, not model quality or accuracy gains.

## Research inspiration

BranchForge draws on the idea of exploring and evaluating alternative model-generated paths described in [*Tree of Thoughts: Deliberate Problem Solving with Large Language Models*](https://arxiv.org/abs/2305.10601) by Shunyu Yao et al. (NeurIPS 2023). BranchForge applies this idea to Python program candidates, using visible-test feedback to guide bounded search and refinement. Its beam search and sequential UCT MCTS are engineering adaptations for this setting; the project does not reproduce the paper's experiments or establish the same performance gains.

## Install

Requires Python 3.12+, uv, and a running Docker daemon (Docker Desktop works on Apple Silicon). From this checkout:

```sh
uv sync
docker pull python:3.12-slim
```

No API credentials are needed for the fake provider. Candidate code still runs inside Docker. Docker failures never trigger host execution.

## Run

```sh
uv run branchforge solve --problem examples/problems/max_subarray.yaml --algorithm beam --parallel-agents 4 --config configs/default.yaml
uv run branchforge solve --problem examples/problems/max_subarray.yaml --algorithm beam --parallel-agents 1 --config configs/default.yaml
uv run branchforge solve --problem examples/problems/max_subarray.yaml --algorithm mcts --config configs/default.yaml
uv run branchforge solve --problem examples/problems/max_subarray.yaml --algorithm baseline
uv run branchforge solve --problem examples/problems/max_subarray.yaml --algorithm best-of-n
uv run branchforge inspect RUN_ID
uv run branchforge benchmark --suite examples/benchmarks/smoke.yaml --algorithms baseline,best-of-n,beam,mcts --config configs/default.yaml
```

`solve` prints the run ID, termination reason, selected candidate, usage, concurrency statistics, and artifact path. Ctrl-C saves partial results after cleanup. `inspect` displays lineage, pruned nodes, worker assignments, rewards, MCTS statistics, and final selection. Run artifacts are inspectable but cannot be resumed.

For a real model, set your provider's credential in your shell and use the real configuration:

```sh
export OPENAI_API_KEY='your-key'
uv run branchforge solve --problem examples/problems/max_subarray.yaml --algorithm beam --parallel-agents 4 --config configs/real.yaml
```

LiteLLM model identifiers can be changed with `--model` or in YAML; provider credentials remain environment-only. Do not commit keys. `--provider litellm` chooses the real adapter; `fake` chooses fixtures. Request retries are bounded and count against call limits. Provider-specific sampling parameters are omitted unless configured. Live API calls are not part of automated validation.

## Architecture

BranchForge generates Python candidates in isolated branch histories, evaluates them in
Docker, and uses visible-test feedback to guide bounded search. Beam search commits
results in deterministic assignment order; MCTS runs sequentially.

See [architecture and search semantics](docs/architecture.md) for components, search
policies, evaluation rules, budget accounting, persistence, and benchmarking.

CLI options override YAML settings, which override defaults. Use
[`configs/default.yaml`](configs/default.yaml) for fake fixtures or
[`configs/real.yaml`](configs/real.yaml) for LiteLLM. Real providers require
`max_tokens: null`; hard dollar ceilings are unsupported. Runs record usage and partial
results, but interrupted computation cannot resume.

## Validation

```sh
uv run pytest -q
uv run pytest -m docker -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

Unit tests use injected executors that recognize fixture labels and never run generated Python. Concurrency tests use an event barrier. Docker integration tests run reference solutions against visible and hidden cases, plus wrong answers, syntax errors, exceptions, timeouts, and memory failures. Docker tests skip explicitly if the daemon or image is unavailable.

## Security and limitations

Containers have networking disabled, a non-root user, no capabilities, no privilege escalation, resource limits, a read-only root, and bounded writable temporary storage. Only a read-only candidate file is mounted; credentials and the Docker socket are not mounted. Captured output is bounded. Containers are forcibly removed after completion or cancellation.

Docker is not an absolute security boundary. Use a dedicated machine or stronger isolation for hostile workloads. The image tag is mutable; record/pin an image digest for controlled experiments. Per-test timeout includes container start/attach overhead. Python allocation failure can appear as a runtime error when the kernel does not report an OOM kill. Cleanup can fail if Docker itself becomes unavailable; inspect containers with the `branchforge-` name prefix after daemon recovery.

Distributed workers, training, parallel MCTS, and resuming interrupted searches are outside the current scope.

## Search execution dashboard

The local, read-only dashboard loads `runs/` automatically. It provides candidate trees,
code inspection and parent diffs, deterministic event replay, worker activity and analytics.
New runs record schema-v2 events; old runs retain their final tree and recorded task timelines,
but detailed replay controls are disabled rather than inventing intermediate states.

```sh
uv sync --locked
uv run uvicorn branchforge.api.app:app --host 127.0.0.1 --port 8000
# In another terminal (Node 24+):
cd dashboard
npm ci
npm run dev
```

Open the URL printed by Vite. Bookmark `/runs/{run_id}` to return to a run. Set
`BRANCHFORGE_RUNS_DIR` on the API process to read a different artifact directory.
The frontend proxies `/api` locally; no credentials or cloud services are needed.

Generate actual search artifacts with the existing fake provider (Docker required):

```sh
uv run branchforge solve --problem examples/problems/max_subarray.yaml --algorithm beam --parallel-agents 4
```

Or generate clearly labeled synthetic test data without Docker or an API key:

```sh
uv run python scripts/dashboard_fixture.py
```

This creates `runs/synthetic-dashboard` with 500 candidate nodes plus the root,
5,000 events and eight simulated workers. It overwrites only this named fixture.
It is test data, not evidence of algorithm quality.

```sh
uv run pytest -q
cd dashboard
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

See [dashboard event compatibility](docs/dashboard.md) for recording semantics and limitations.

## LiveCodeBench research pipeline

See [the LiveCodeBench guide](docs/livecodebench.md) for pinned dataset/checker versions,
manifest preparation, credential-free validation, spending-gated real experiments,
reports, and the dashboard's `/experiments` view. No paid calls are required to test
or preview the pipeline.

### Local Claude Code / Codex integration

The [local plugin guide](docs/local-plugin.md) covers installing a prepared wheel,
registering the skills and stdio MCP server, provider credentials, bounded jobs, and
the packaged dashboard. Developers prepare distributions with
`python scripts/prepare_release.py` followed by `uv build`. Users with the installed
runtime can run `branchforge demo` and `branchforge dashboard` without Node.
