# Architecture and search semantics

This document describes BranchForge’s search engine, evaluation, budget accounting, and persisted artifacts. For installation and commands, see the [README](../README.md). The [local plugin guide](local-plugin.md) covers MCP job ownership and lifecycle, and the [dashboard guide](dashboard.md) covers event replay.

## Components and search semantics

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
