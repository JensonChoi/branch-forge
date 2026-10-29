# Dashboard recording and compatibility

The API is a local read-only FastAPI adapter over JSON/JSONL artifacts. It never imports
candidate code. React Flow renders candidate relationships; timeline rows represent worker
tasks. Candidate strategy and explanation are recorded model outputs, not private reasoning.

## Event schema v2

Every new event retains its original fields and adds `schema_version: 2`. Logical `sequence`
orders replay; UTC timestamps measure overlaps. They are not interchangeable with depth.

- `RUN_STARTED.root` contains the initial root snapshot.
- `BRANCH_TASK_CREATED.frontier_index` associates a task with its expansion frontier.
- `SUBAGENT_STARTED.worker_id` identifies a pool slot reused across tasks. Historical v1
  worker IDs equal task IDs; the UI displays those as task lanes.
- `LLM_STARTED` occurs after admission to the LLM limiter; `LLM_FINISHED` records returned
  input/output tokens and nullable cost. `LLM_FAILED` records a failed attempt. The older
  `SUBAGENT_LLM_REQUESTED` event remains the request intent before admission.
- `CANDIDATE_GENERATED` includes the candidate and parent ID. It appears provisionally
  before tree commitment. `EVALUATION_STARTED` and `CANDIDATE_EVALUATED.evaluation`
  describe the actual evaluation lifecycle.
- `NODE_CREATED.node` contains the committed snapshot. Commit order remains deterministic
  and is independent of worker completion order.
- Existing pruning and backpropagation events update replay state at their sequence.
- `FINAL_SELECTED` records the chosen node (possibly null), independently of visible success.

Final inspection uses the final tree. Replay uses only event payloads; final values are never
injected into earlier states. Checkpoints every 100 events support backward steps and seeking.
Legacy traces expose final inspection and supported timelines; detailed replay is disabled.
Malformed/duplicate events are omitted with warnings and sequence gaps disable detailed replay.
Unknown events do not change replay state. Unknown costs remain null rather than zero.

Task intervals missing a terminal event remain open. Nested activities interrupted by task
termination remain incomplete unless their own completion was recorded. Peak concurrency
uses complete task intervals; with incomplete logs it describes only the recorded intervals.
Idle time is not reported because worker lifetimes are not recorded. The token curve counts
recorded completed responses, including responses whose generated content fails validation.

## Development and tests

Use the commands in README. Python tests cover the API, filesystem containment, corrupted
artifacts, timeline arithmetic, and new trace fields across all algorithms. Vitest tests replay
and checkpoints; Playwright loads the synthetic fixture and exercises the dashboard flow.
Monaco and its worker are bundled locally, so inspecting code does not require a CDN.
The frontend and API run as separate local processes; hosted deployment and live monitoring
are intentionally excluded.

## Current presentation limits

Run-history sorting and text filtering apply to the current 100-run page. The API exposes
pagination for larger directories. Full-tree overview can make individual nodes tiny on the
500-candidate fixture; selecting a candidate centers and zooms the canvas. Monaco's lazy
bundle is large, and Vite reports a chunk-size warning. Worker idle time and unrecorded legacy
request activity remain unavailable. These limitations do not change recorded search results.
