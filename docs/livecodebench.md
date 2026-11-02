# LiveCodeBench experiments

This milestone adds a benchmark adapter, a six-variant experiment runner, an isolated official checker, reproducible selections, statistical reports, and a dashboard experiment view. The sixth variant is the additional one-call baseline; the five requested search configurations remain unchanged.

A user-authorized $5-capped real-model smoke test has completed (see the recorded results below). The separate report under `runs/experiment-fixture/` remains scripted fixture data, not research evidence.

## Pins and selection

- Dataset: `livecodebench/code_generation_lite`, `release_v6`, revision `0fe84c3912ea0c4d4a78037083943e8f0c4dd505`.
- Official checker: LiveCodeBench revision `28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24`, `evaluate_generations_by_problem`, Python 3.12 container, NumPy 2.2.6, tqdm 4.67.1. Each experiment records the built image ID.
- The official loading script lists releases v1–v6; the dataset card only documents v1–v5. We read the six pinned JSONL files directly instead of executing a remote dataset loader.
- Seed 42, equal allocation over joint difficulty/platform/publication-month strata, redistributing exhausted strata. This is balanced stratified sampling, not an estimate weighted to the source population.
- The local `runs/lcb-manifest.json` records full public problems, exact IDs, exclusions, and source-file SHA-256 hashes. It contains 29 easy, 35 medium, and 36 hard problems; 51 LeetCode, 46 AtCoder, 3 Codeforces; 51 function-based submissions. `abc350_c` is excluded because it has no public samples. Algorithmic categories are unavailable.
- This release predates the selected model's documented knowledge cutoff. Results must be called contamination-risk-aware, never contamination-free. The manifest does not prove non-exposure.

Sources: [official repository](https://github.com/LiveCodeBench/LiveCodeBench), [pinned loader](https://huggingface.co/datasets/livecodebench/code_generation_lite/blob/0fe84c3912ea0c4d4a78037083943e8f0c4dd505/code_generation_lite.py), [dataset card](https://huggingface.co/datasets/livecodebench/code_generation_lite).

## Model and resources

`configs/livecodebench.yaml` selects `openai/gpt-5.4-mini-2026-03-17` through LiteLLM, medium reasoning, temperature omitted, 4,096 maximum completion tokens, 32,000 prompt characters, four concurrent requests, 120-second request timeout, and zero retries by default. The documented knowledge cutoff is August 31, 2025. GPT-5 mini was the initial recommendation but current documentation marks it deprecated; the example uses GPT-5.4 mini instead. [Model documentation](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

All five iterative configurations receive ceilings of eight physical requests (including any configured retries), eight candidates, and 180 seconds. Single-shot gets one request/candidate. Sequential and parallel beam differ only in worker concurrency. Best-of-N uses eight independent branches. Reasoning tokens, reported model identifiers and fingerprints are captured when returned by the provider; reasoning tokens are already included in output tokens and are not added twice.

The existing runtime does not guarantee real-provider token admission: `max_tokens` and `max_cost_usd` remain null. The experiment-level spending check conservatively bounds all scheduled physical requests using UTF-8 prompt bounds, a framing allowance, completion limits, and configured upper-bound token prices. It refuses a run unless this ceiling fits an explicit `spending_limit_usd`. Prices must be reviewed for provider/account surcharges. Defaults use $0.75/M input and $4.50/M output; actual costs come from returned usage/LiteLLM pricing, and unknown billing stays unknown. Missing usage and failed requests can leave token accounting incomplete. No exact matched-realized-compute claim is made.

At these settings, conservative ceilings are $96.35328 for validation, $240.88320 for pilot, and $481.76640 for primary, per repetition. These deliberately pessimistic ceilings are not predicted bills. Actual costs require live usage. The configured model authenticated and returned usage in the smoke test; some responses exhausted the completion allowance on reasoning without returning code.

## Setup and validation

```sh
uv sync --locked
docker build -t branchforge-lcb:28fef95 docker/livecodebench
uv run branchforge experiment-prepare runs/lcb-cache runs/lcb-manifest.json --download-data
uv run branchforge experiment-fixture
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv build
```

The dataset download is about 4.2 GiB. Existing complete cache files are reused. Preparation refuses to overwrite a manifest; keep the existing one or use a new destination. Fixture generation similarly requires a new output path (`--output runs/experiment-fixture-2`). No credentials are needed for these steps.

## Paid stages, only after authorization

Set `OPENAI_API_KEY` in the local process environment. Never place it in a config or paste it into a report. Copy the example to `configs/lcb-validation.yaml`, `configs/lcb-pilot.yaml`, and `configs/lcb-primary.yaml`; set `stage` to `validation`, `pilot`, and `primary`, respectively. Set an approved `spending_limit_usd` in each copy. Review model difficulty/cost with validation and pilot before freezing primary settings. Repetitions use `trials`; increasing this multiplies the ceiling.

```sh
uv run branchforge experiment-plan configs/lcb-validation.yaml
uv run branchforge experiment-run configs/lcb-validation.yaml runs/lcb-manifest.json runs/lcb-cache runs/experiment-validation --allow-paid
uv run branchforge experiment-plan configs/lcb-pilot.yaml
uv run branchforge experiment-run configs/lcb-pilot.yaml runs/lcb-manifest.json runs/lcb-cache runs/experiment-pilot --allow-paid
uv run branchforge experiment-plan configs/lcb-primary.yaml
uv run branchforge experiment-run configs/lcb-primary.yaml runs/lcb-manifest.json runs/lcb-cache runs/experiment-primary --allow-paid
uv run branchforge experiment-report runs/experiment-primary
```

Validation uses the first 20 manifest entries, pilot 50, primary 100. The overlap is explicit; private diagnostics never reach agents. Only binary outcomes and sanitized error codes leave the private grader. Human tuning after viewing private outcomes can still bias a study and must be disclosed.

Repeat the same run command to resume. A process lock prevents concurrent writers. Completed trials are skipped, and frozen selections are graded without regeneration. An interrupted search with a saved result is recovered; a hard crash without a result becomes an interrupted, unknown-grade attempt with unknown resource usage. It is never silently regenerated. Cancellation checkpoints the search and stops scheduling. Configuration, selection, source contents, commit, package versions, and grader image must match the frozen manifest. Use a new labeled experiment for protocol changes.

## Reports and dashboard

Outputs include `report.md`, locally viewable `report.html`, `summary.json`, `configuration.json`, `problem_manifest.json`, `per_problem_results.csv`, PNG/SVG figures, and per-run case-study files. Single-trial rates use Wilson intervals; repeated-trial and paired intervals bootstrap whole problem groups (2,000 draws, seed 42). Paired resource differences use available matched pairs and expose sample counts. Unknown grades count as unsolved in end-to-end solve rate; missing grades and incomplete experiment counts are explicit. Cost per solve is undefined for zero solves. Case studies prioritize disagreements across up to five distinct problems and are exploratory.

```sh
uv run uvicorn branchforge.api.app:app --host 127.0.0.1 --port 8000
# In another terminal:
cd dashboard
npm install
npm run dev
```

Open `http://localhost:5173/experiments`, choose an experiment, and follow its replay links. Store experiment directories directly under the configured runs directory with an `experiment-` prefix. API routes are `/api/experiments` and `/api/experiments/{experiment_id}`.

## Validation recorded

- Full Python suite: 46 passed, including official Docker checker compatibility and six-variant fixture integration; no Docker skips.
- Ruff lint/format and mypy passed; source/wheel build passed.
- Dashboard: six unit tests, three Playwright tests, and production build passed. Browser tests include experiment selection and replay navigation.
- Generated `runs/experiment-fixture/report.html` and inspected the exported solve-rate figure. Its six solved submissions are scripted validation only; actual API spending is $0.
- Remaining warnings: existing FastAPI/httpx deprecation and large dashboard bundle chunks.

## Limits of the delivered evidence

The 50-problem pilot and 100-problem primary experiments remain unexecuted. The completed reduced Stage A is recorded below. The two-problem smoke test validates connectivity and grading, not comparative algorithm quality. Output-token sizing, rate limits at scale, and model difficulty fit still need validation. There is no human-reviewed conceptual failure diagnosis: automatic reports expose runtime evidence and leave causal interpretation to review. Repeated seeds identify trials but do not guarantee deterministic provider sampling. Bootstrap intervals on very small samples can be degenerate. The checker has per-test timeouts and an outer container timeout; an outer timeout is an unknown infrastructure/censoring outcome, not a proven wrong answer.


## Authorized real-model smoke test

Using `configs/livecodebench-smoke.yaml`, stage `smoke` selects the first two manifest entries, `3264` (function-based) and `abc382_b` (stdin/stdout). Each iterative configuration has two requests/candidates; single-shot has one. The $5 experiment cap admitted a conservative maximum of 22 requests / $2.585088. The secret was loaded into the run process environment from the user-provided local file and was not saved to artifacts.

All 12 trials completed: 11 passed official grading and one produced no candidate. Fourteen physical API requests returned usage: 9,898 input tokens, 24,114 output tokens (including 20,034 reasoning tokens). Usage-based cost was **$0.1159365**, not an invoice verification. No further paid requests were made.

Two requests used all 4,096 completion tokens on reasoning and returned empty output. One caused the function-problem beam-parallel trial to produce no candidate; the other was in best-of-N, where another candidate passed. These observations do not establish an algorithm ranking, and the tight smoke budget does not exercise meaningful parallel search depth. Before a research run, assess a larger completion allowance or lower reasoning effort in a separately labeled protocol.

The smoke test found and fixed a cost-accounting bug: parsing failures had marked billing unknown even when response usage and cost were already recorded. The regression suite now retains those known costs. `runs/experiment-live-smoke/cost-audit.json` reconciles every dispatched request with its returned usage and records event hashes. `trials.original.json` preserves original trial data; regenerated `trials.json`, reports, and charts contain corrected cost totals without changing outcomes. Raw search artifacts and the original generation protocol remain unchanged. The completed run cannot be resumed under changed source hashes; this is intentional.

View `runs/experiment-live-smoke/report.html`, or select `experiment-live-smoke` at `/experiments`. Re-render without API calls:

```sh
uv run branchforge experiment-report runs/experiment-live-smoke
```

## Stage A with an enforced $5 cap

`configs/livecodebench-validation.yaml` raises the completion allowance to 8,192 tokens, retains medium reasoning and the original eight-request/eight-candidate search budgets, and selects `spending_mode: per_request` with `spending_limit_usd: 5.0`. The target is 20 manifest problems across six configurations (120 trials). The $5 cap is separate from the prior smoke test.

Unlike whole-experiment preflight admission, per-request mode reserves the maximum possible charge immediately before each network dispatch. Text prompt UTF-8 byte bounds plus framing allowance and the completion ceiling determine the reservation using the configured upper-bound rates. Reservations are saved to `spending.json` before dispatch and synchronized across workers. Returned usage releases unused capacity; missing usage, transport failures, cancellation, and hard crashes retain their reservation. A provider pricing/token bound violation stops further requests. The guard does not alter OpenAI account-level billing settings.

If the remaining cap cannot reserve another request, further scheduling stops and the report shows an incomplete experiment. It never claims all 20 problems were validated unless all scheduled trials completed. Zero-retry defaults prevent automatic resubmission of empty outputs. `finish_reason` is now saved alongside response usage to diagnose completion truncation.

```sh
uv run branchforge experiment-plan configs/livecodebench-validation.yaml
# After loading OPENAI_API_KEY into the process environment:
uv run branchforge experiment-run configs/livecodebench-validation.yaml runs/lcb-manifest.json runs/lcb-cache runs/experiment-stage-a --allow-paid
```

The cost guard was tested for concurrent oversubscription, unused-reservation reconciliation, and failure recovery across process restarts. The pre-run Python suite passed 49 tests; Ruff and mypy also passed.

## Completed reduced Stage A

The user reduced Stage A to one configuration per remaining problem. The expanded comparison was stopped, four completed baseline trials were reused with provenance, and the remaining sixteen problems ran baseline only. `runs/experiment-stage-a-reduced/` contains the completed 20/20 report and `provenance.json`; the earlier comparison remains in `runs/experiment-stage-a/`. Both share the original $5 stage ledger.

Results: 13 official passes, two official failures, four trials with no candidate, and one unknown grade after the grading container reached its memory limit. Five of the baseline's 28 requests exhausted all 8,192 completion tokens on reasoning and returned empty output; one such request occurred after an earlier candidate, so only four trials lacked a final candidate. Raising the completion ceiling did not eliminate truncation.

The twenty baseline trials have $0.3609297 in recorded usage cost. Total Stage A costs including the earlier expanded comparison are $1.0698312 in returned-response usage, with $1.163984 conservatively accounted for after retaining reservations for two unresolved requests from the interrupted run. These are usage-based costs, not invoice verification, and exclude the prior $0.1159365 smoke test. The $5 cap was not reached.

Execution and report generation completed before the conversation interruption. No Stage B or Stage C run was launched. Before progressing to the pilot, investigate output truncation, enforce the generation schema, and resolve the grader memory issue. This validation run is not evidence of comparative algorithm quality. The implementation and validation notes are maintained on `feat/livecodebench-report`.
