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

`configs/livecodebench.yaml` selects `openai/gpt-5.4-mini-2026-03-17` through LiteLLM, medium reasoning, temperature omitted, 25,000 maximum completion tokens, 32,000 prompt characters, four concurrent requests, 120-second request timeout, and zero retries by default. The documented knowledge cutoff is August 31, 2025. GPT-5 mini was the initial recommendation but current documentation marks it deprecated; the example uses GPT-5.4 mini instead. [Model documentation](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

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

Validation uses the first 20 manifest entries. Under the amended protocol, primary uses the first 50 entries; no separate pilot is required. The overlap is explicit; private diagnostics never reach agents. Only binary outcomes and sanitized error codes leave the private grader. Human tuning after viewing private outcomes can still bias a study and must be disclosed.

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

The amended 50-problem primary evaluation remains unexecuted. The completed reduced Stage A is recorded below. The two-problem smoke test validates connectivity and grading, not comparative algorithm quality. Output-token sizing, rate limits at scale, and model difficulty fit still need validation. There is no human-reviewed conceptual failure diagnosis: automatic reports expose runtime evidence and leave causal interpretation to review. Repeated seeds identify trials but do not guarantee deterministic provider sampling. Bootstrap intervals on very small samples can be degenerate. The checker has per-test timeouts and an outer container timeout; an outer timeout is an unknown infrastructure/censoring outcome, not a proven wrong answer.


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


## Current completion allowance

All `configs/livecodebench*.yaml` configurations now allow 25,000 completion tokens per request, with medium reasoning unchanged. Saved smoke and Stage A manifests retain their original 4,096/8,192-token protocols; results above refer to those historical settings. Future executions require a new experiment directory. Existing $5 limits remain in the smoke and validation configurations; per-request reservations include the higher completion ceiling. Historical whole-run cost ceilings above must be recalculated with `experiment-plan` for current settings. This configuration update does not execute paid requests or change grader memory.


## Grader-memory and response-schema follow-up

The frozen `abc362_c` submission was regraded without regeneration or model calls. At 512 MiB, Docker again reported an OOM kill. At 1,024 MiB, the official checker completed with `FAIL` (error code -2). A trivial `print(0)` control also OOM-killed at 512 MiB, demonstrating that the original submission's algorithm is not required to trigger the failure; checker/test-loading overhead contributes. The exact allocation responsible was not profiled. Use a 1 GiB grading container for this submission's follow-up; broader grading-memory policy remains a separate configuration decision.

`runs/experiment-stage-a-reduced/memory-regrade.json` records the code hash, original run ID, memory limits, sanitized grading outcomes, and timings. The original Stage A report and its unknown grade remain unchanged; the follow-up resolves that submission to an official failure under the larger container limit. No private test diagnostics entered search contexts.

The LiteLLM adapter now requests strict JSON Schema output with all three generation fields required on the wire: `strategy` is a string or null; `explanation` and `code` are strings; additional fields are forbidden. Local validation also rejects extra fields and coercions. Provider schema rejection remains an explicit error rather than silently falling back to unrestricted text. Truncated responses can still violate the schema; their returned token usage remains accounted for. The spending guard includes schema bytes when reserving request cost.

Credential-free tests cover the exact outgoing schema, the previously observed list-valued strategy, unexpected fields, invalid code types, and retained usage for truncated output. Live provider schema adherence has not been retested with a paid request. See [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Targeted 25,000-token follow-up

`configs/livecodebench-truncation-followup.yaml` selects the five Stage A problems that previously exhausted their completion allowance. It uses baseline only, medium reasoning, strict JSON Schema, 25,000 completion tokens, a 1 GiB checker container, a 300-second request timeout, a 360-second per-task limit, and a 600-second trial limit. The follow-up has its own persistent $5 spending guard. Selection is outcome-based and exploratory; it is not a fresh random sample or an algorithm comparison.

All five trials completed. `abc306_e`, `arc194_d`, and `3686` passed official grading, using 9,298, 16,482, and 10,146 completion tokens respectively. `3233` again exhausted the entire 25,000-token allowance on reasoning and returned no code. `abc350_e` returned eight schema-valid candidates, exhausted its candidate budget, and failed final grading. The user requested skipping that last problem, but the trial had already finished when the stop check ran; its actual completed outcome is retained.

Twelve requests returned usage, with no unresolved requests. Recorded API cost was $0.59354985; the conservative ledger accounting was $0.609191, below the $5 cap. One response was truncated; the eleven complete responses passed schema validation. No checker-memory errors occurred. Trial latencies were approximately 47, 91, 51, 135, and 414 seconds. Higher completion limits reduce truncation on this selected set but do not guarantee output, correctness, or repair success. Model sampling, schema, timeout, and checker-memory settings differ from Stage A, so outcomes do not isolate a single causal change.

Artifacts are under `runs/experiment-truncation-followup/`, including `manifest.json`, `spending.json`, `trials.json`, `report.md`, and `report.html`. Source changes add explicit follow-up IDs and an optional checker-memory override. Pre-run validation passed the existing 53-test suite and 12 experiment tests including the two new follow-up checks, plus Ruff and mypy. No Stage B run was launched.


## Amended primary protocol: one 50-problem evaluation

At the user's request, the required 50-problem pilot and 100-problem primary sequence is replaced by a single 50-problem primary evaluation. Use `configs/livecodebench-primary.yaml` with the first 50 IDs of the existing seed-42 manifest, chosen without filtering for previous outcomes. All five requested configurations run on the same IDs: single trajectory, best-of-N, sequential beam, parallel beam, and sequential MCTS. One repetition produces 250 trials. The extra single-shot comparison is omitted from this condensed evaluation.

The model is `openai/gpt-5.4-mini-2026-03-17`, medium reasoning, 25,000 completion tokens, strict schema, and a 1 GiB checker. Search budgets, timeouts, and statistics follow the tested configuration. Freeze these settings before launching; any subsequent policy changes require a separately labeled follow-up. Fifty problems yield wider uncertainty intervals than 100, so small paired differences may remain inconclusive. The first 50 include previously used validation problems: disclose this overlap and human protocol tuning as a limitation. Do not describe them as an untouched holdout.

Set an explicitly approved spending limit before execution. The supplied primary config leaves that limit unset and cannot launch paid requests until it is configured. `experiment-plan configs/livecodebench-primary.yaml` shows the schedule and conservative request ceiling. The legacy `pilot` stage remains available for optional diagnostics, but it is no longer a required step. Historical records and the original milestone prompt retain their original stage definitions.


## LeetCode 3233 single-request 50,000-token diagnostic

At the user's request, `configs/livecodebench-3233-50k.yaml` selects only `3233` for a separately labeled baseline diagnostic, with medium reasoning, strict schema, a 50,000-token completion allowance, no retries, one request/candidate, a 360-second request timeout, and a $0.30 per-request spending cap. Other primary settings remain unchanged.

The single request returned after approximately 262.8 seconds with `finish_reason: length`: all 50,000 completion tokens were reasoning tokens, and no visible code was returned. There was no candidate to grade. Input usage was 1,005 tokens; recorded cost was $0.22575375, within the $0.30 cap. No retries or additional API requests were made. Artifacts are in `runs/experiment-3233-50k/`.

This result does not establish that the model cannot solve the problem, but further automatic ceiling increases are not justified by this diagnostic. Keep the primary protocol's uniform 25,000-token limit and retain this problem's failure in evaluation rather than excluding it based on outcomes.

The user accepted this decision: retain the uniform 25,000-token primary allowance, keep LeetCode 3233 in the existing 50-problem selection, and stop further higher-limit diagnostics for it. The 50,000-token configuration is a completed historical diagnostic, not a primary setting.


## Authorized primary evaluation launch

The user authorized up to $12.86 of API credit for the condensed primary evaluation. `configs/livecodebench-primary.yaml` now sets that cap with persistent per-request admission. The run uses the existing first 50 seed-42 problems, all five configurations, one repetition (250 planned trials), the pinned GPT-5.4 mini snapshot, medium reasoning, 25,000 completion tokens, strict schema, and a 1 GiB checker. No earlier trial outcomes are reused as primary results.

Artifacts are checkpointed in `runs/experiment-primary/`: `primary-selection.json`, `manifest.json`, `source-snapshot.tar.gz`, `trials.json`, `summary.json`, `spending.json`, and `runner.log`. The runner generates HTML/Markdown reports on completion or a spending stop. `watch-status.json` records process status and observed cost; the local watcher attempts a desktop notification on credit exhaustion or process exit. This watcher makes no API calls and cannot send a new chat message while the assistant is idle.

The adapter now classifies explicit provider credit/quota exhaustion and stops further scheduling via the shared ledger. Unknown charges retain their maximum reservation. Recorded returned-response cost can be lower than conservative ledger accounting; neither is invoice verification. Current official pricing was checked before launch. The initial credential-free checks passed 56 tests, Ruff, formatting, and mypy; the credit-stop addition passed nine targeted schema/spending tests and mypy.

This section records launch, not completion. Consult `watch-status.json` and `summary.json` for the saved run state; incomplete results must remain labeled incomplete. Source and protocol changes are prohibited while this primary run is active.


## Uncapped primary continuation

After the primary runner stopped at 192/250 trials, the user added API credit and explicitly authorized removing the dollar cap to finish the remaining 58 trials. The primary config now uses `spending_mode: unlimited` and a null spending limit. Call/candidate/time budgets, model, reasoning effort, completion limit, problem IDs, all search policies, and grading settings remain frozen.

`runs/experiment-primary/before-uncapped-resume/` preserves the original partial report, manifest, ledger, and trial records. `manifest.initial.json` retains the initial protocol, `resume-authorization.json` records the funding-only amendment and authorized source hash, and `source-snapshot-resume.tar.gz` records the administrative resume changes. The source audit compared against the launch snapshot and allowed changes only to runner funding/resume handling, spending accounting, and reporting. Every other Python source file remained identical. The resumed runner skips the 192 completed identities; it does not regenerate prior candidates or feed grading outcomes back to search.

Unlimited mode continues durable request/usage accounting and stops further scheduling on explicit provider credit exhaustion, but has no dollar ceiling. Unresolved historical requests remain recorded conservatively. The ledger funding amendment clears only the prior spending-limit stop. The completion watcher follows the new process; final reports and CSV exports are regenerated when the resumed process ends. Validation passed 60 tests, Ruff, formatting, and mypy before restarting; no primary research settings were changed.
