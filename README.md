# BranchForge

BranchForge is a local Python harness for exploring candidate solutions with explicit trees, objective visible-test feedback, and bounded inference budgets. It supports single-trajectory refinement, independent best-of-N sampling, synchronized sequential/parallel beam search, and sequential UCT MCTS.

Search improving reliability is an experimental question. Included fake-provider fixtures demonstrate runtime behavior, not model quality or accuracy gains.

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

## Architecture and semantics

- `models.py`: typed, visible-only runtime inputs, immutable candidates/evaluations, and a single tree registry.
- `search.py`: policies and the orchestrator that validates and commits worker results.
- `agents.py`: independent local histories and a bounded asyncio worker pool. A worker is temporary execution capacity; a candidate is a persistent node.
- `llm.py`: provider protocol, LiteLLM adapter, bounded prompts, and scripted fake responses.
- `execution.py`: Docker lifecycle, output limits, comparison, and duplicate evaluation cache.
- `runtime.py`: quotas, event sequencing, atomic snapshots, and concurrency controls.
- `benchmark.py`, `cli.py`: held-out reporting and terminal tools.

Beam expands each parent into at most `branching_factor` independent task chains. Each chain is limited by depth, per-task candidate count, refinement steps, calls, and time. Local refinements are separate nodes. All assigned tasks settle before results are committed in assignment order; faster workers receive no additional work. All valid candidates from the frontier are ranked by reward then creation order; at most `beam_width` survive. Older frontiers are not carried forward. A visible success finishes its chain but never cancels its sibling tasks.

Sequential beam uses the same algorithm and refinement limits with worker concurrency one. Independent limits govern workers, provider requests, and containers. MCTS expands one child per simulation, uses direct visible reward as its shallow rollout, and backpropagates once along the path. Final selection uses direct reward, not accumulated MCTS value.

The baseline refines one path. Best-of-N generates independent root children without shared feedback. Default fake responses intentionally include failures; they are not a useful accuracy baseline. The scripted dynamic-programming branch reaches packaged reference code after feedback.

Visible reward is passed tests / total tests. Invalid infrastructure evaluations have no reward. Output comparison normalizes CRLF/CR to LF, strips trailing whitespace on each line and at the end, and preserves internal whitespace. Syntax errors are runtime failures. Source text is never executed or imported by the host process. Exact duplicate source evaluations are cached within an evaluator; lineage and call consumption remain visible.

## Configuration and budgets

CLI overrides YAML; YAML overrides defaults. Unknown keys and incompatible explicit concurrency options are rejected. See `Config` and its nested models for the full validated schema. `configs/default.yaml` runs fake fixtures; `configs/real.yaml` configures LiteLLM.

The central budget reserves per-task call and candidate capacity in stable assignment order before dispatch. Earlier assignments receive available capacity when a frontier cannot fit. Unused capacity is reconciled at the barrier. Calls, including retries, are charged at dispatch; candidates are charged after valid structured generation. Evaluations count candidate evaluations including cache hits. Costs are reported only when the adapter can price returned usage.

Strict token reservations are supported for the fake provider's defined accounting. Real providers require `max_tokens: null`: this version cannot guarantee a provider-independent preflight token bound. Hard dollar ceilings are rejected rather than silently ignored. Real runs are bounded by calls, candidates, output tokens, time, and concurrency. Requests canceled or failed before a usage response may incur unreported provider usage; consult provider billing. These limits are explicit MVP constraints.

Prompts include the original problem, an optional hint, and as many recent ancestors as fit the character bound. Oversized problems fail rather than being silently truncated. No sibling conversation or hidden test is passed to workers. Strategy hints are suggestions, not algorithm mandates.

## Persistence and benchmarking

Each run stores `config.json`, visible-only `problem.json`, `events.jsonl`, `tree.json`, and `result.json` under `runs/RUN_ID`. Events carry actual timestamps and monotonically increasing sequence numbers. Tree commits follow deterministic task order. Partial runs preserve generated candidates even when evaluation is interrupted.

Benchmark suites reference visible problems and separate hidden-test files. Hidden cases are loaded only after selection. Benchmark outputs contain trials and summary metrics; hidden cases are absent from search artifacts. Beam expands into sequential and parallel variants automatically. Set `repeats` in the suite for repeated trials. Use identical model, test splits, refinement settings, and comparable call/token budgets across variants. Compare both usage and latency; do not interpret fake results as research evidence. The seed is recorded metadata, not a guarantee of provider determinism.

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

Future milestones: reliable provider-specific token/cost admission, stronger sandbox backends, larger held-out benchmarks, and checkpoint resume. No web UI, distributed workers, training, or parallel MCTS is included.
