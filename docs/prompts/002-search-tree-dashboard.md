# BranchForge — Interactive Search Tree Dashboard

## 1. Project Overview

Extend the existing **BranchForge** agentic tree-search harness with a modern, interactive web dashboard for visualizing, inspecting, and replaying LLM search executions.

BranchForge is a Python-based agentic harness supporting:

- Single-trajectory reasoning.
- Best-of-N independent sampling.
- Sequential beam search.
- Parallel-subagent beam search.
- Sequential Monte Carlo Tree Search (MCTS).
- Objective evaluation of generated Python code.
- Search-tree persistence.
- Structured execution event logs.
- Configurable inference budgets.

The dashboard should expose the internal behavior of these search algorithms in a way that is intuitive, visually compelling, and useful for debugging.

### Primary Goal

Build an **interactive search execution debugger** that makes it possible to answer:

1. What branches did the LLM explore?
2. Which subagents were running concurrently?
3. What candidate solutions did they generate?
4. Why did particular candidates succeed or fail?
5. How did evaluation feedback influence subsequent refinements?
6. Why were certain branches pruned?
7. How were inference tokens, costs, and execution time distributed?
8. How did the search algorithm arrive at its final selected solution?

The dashboard must reconstruct actual execution behavior from persisted run artifacts.

Do not fabricate search events, candidate scores, subagent activity, or execution metrics.

---

## 2. Major Features

Implement six primary features:

1. Run history and run selection.
2. Interactive search-tree visualization.
3. Historical execution replay.
4. Concurrent subagent activity timeline.
5. Detailed node and candidate inspection.
6. Search analytics and performance metrics.

The dashboard should support all existing BranchForge search algorithms, with particularly strong visualization for parallel-subagent beam search.

### Non-Goals

Do not implement:

- A new LLM agent framework.
- New search algorithms.
- Distributed worker infrastructure.
- Authentication or multi-user accounts.
- Cloud deployment.
- Remote code execution from the browser.
- Editing historical search trees.
- Modifying recorded evaluation results.
- A database server.
- Real-time collaborative editing.

Do not replace or rewrite the existing BranchForge search engine.

---

## 3. Technology Stack

### Frontend

Use:

- React 19.
- TypeScript with strict typing.
- Vite.
- React Flow (`@xyflow/react`).
- Tailwind CSS.
- shadcn/ui for reusable interface components.
- Lucide React for icons.
- Recharts for analytics.
- TanStack Query for API state.
- Zustand only if shared visualization state becomes complex.

### Backend

Extend the existing Python project using:

- FastAPI.
- Pydantic.
- Existing JSON/JSONL run artifacts.
- Existing BranchForge domain models.

Use read-only API endpoints for retrieving completed runs and replay data.

### Design Principles

- Clean, modern developer-tool aesthetic.
- Dark mode by default.
- Responsive layout.
- Smooth, restrained animations.
- High information density without visual clutter.
- Consistent colors representing search states.
- Clear distinction between search nodes and subagent workers.
- Efficient rendering for trees with hundreds of nodes.

Avoid unnecessary dependencies and elaborate frontend abstractions.

---

## 4. Application Layout

Build a desktop-first interface resembling a modern developer observability tool.

### Primary Layout

```text
┌────────────────────────────────────────────────────────────┐
│ BranchForge     Run Selector        Algorithm     Settings │
├──────────────┬───────────────────────────────┬─────────────┤
│              │                               │             │
│ Run History  │     Search Tree Canvas        │ Node Detail │
│              │                               │             │
│ Filters      │        Interactive            │ Candidate   │
│              │        Node Graph             │ Code        │
│ Search       │                               │             │
│              │                               │ Evaluation  │
│              │                               │             │
│              │                               │ History     │
├──────────────┴───────────────────────────────┴─────────────┤
│                                                            │
│                   Replay Timeline                          │
│                                                            │
├────────────────────────────────────────────────────────────┤
│ Metrics: Tokens | Cost | Latency | Workers | Success Rate   │
└────────────────────────────────────────────────────────────┘
```

The exact layout may be adjusted for usability.

### Main Regions

**Left Sidebar**

- Run history.
- Search and filters.
- Algorithm selection.
- Run metadata.

**Center Canvas**

- Interactive search-tree graph.
- Pan and zoom.
- Node selection.
- Branch expansion and collapse.
- Graph layout controls.

**Right Inspector**

- Selected node.
- Candidate implementation.
- Test outcomes.
- Reasoning summary.
- Parent-child relationships.
- Evaluation feedback.

**Bottom Timeline**

- Execution replay.
- Playback controls.
- Event timeline.
- Concurrent subagent activity.

**Metrics View**

- Token usage.
- API cost.
- Search depth.
- Candidate counts.
- Evaluation rewards.
- Parallelism statistics.

Make panels resizable where practical.

---

## 5. Run History and Selection

Implement a landing view showing recorded BranchForge executions.

### Run Table

Each run should display:

- Run ID.
- Problem title.
- Search algorithm.
- Model identifier.
- Start timestamp.
- Execution duration.
- Final visible-test reward.
- Hidden-test result, if separately recorded by benchmarking.
- Number of generated candidates.
- Total LLM calls.
- Total tokens.
- API cost, when known.
- Termination reason.

Support sorting and filtering.

### Run Selection

Clicking a run should open its visualization.

Use a route such as:

```text
/runs/{run_id}
```

Support bookmarking and reloading the selected run.

### Run Status

Distinguish:

- Completed.
- Canceled.
- Failed.
- Partially recorded.

If a run has incomplete artifacts, show available information without inventing missing data.

---

## 6. Interactive Search Tree

Use React Flow for the graph visualization.

### Node Representation

Each search node should display:

- Node identifier.
- Candidate strategy.
- Depth.
- Evaluation reward.
- Current or final status.
- Subagent identifier, if applicable.
- Number of children.

Use a compact node design.

### Node Status Colors

Use a consistent semantic palette:

| Status | Color |
|---|---|
| Pending | Neutral gray |
| Expanding | Blue |
| Evaluating | Amber |
| Evaluated | Slate/neutral |
| Failed | Red |
| Pruned | Muted gray |
| Successful | Green |
| Selected final solution | Distinct green border or highlight |

Avoid relying solely on color. Include text, icons, or patterns that remain accessible.

The selected final solution must be visually distinguishable from candidates that merely passed visible tests.

### Tree Edges

Edges represent parent-child candidate relationships.

Support:

- Highlighting the selected node's ancestor path.
- Highlighting refinement chains.
- Distinguishing active from pruned branches.
- Showing parent-child relationships across subagent assignments.

Do not incorrectly use edges to represent communication between independent subagents.

### Graph Layout

Provide:

- Automatic hierarchical layout.
- Left-to-right and top-to-bottom orientations.
- Fit-to-view.
- Zoom controls.
- Pan.
- Node centering.
- Collapsible subtrees.

Use Dagre or ELK for layout.

Make layout stable during historical replay to minimize unnecessary movement.

### Search Algorithm Awareness

For beam search:

- Group nodes by depth or frontier.
- Highlight surviving beam candidates.
- Show pruned candidates.
- Show frontier transitions.

For MCTS:

- Display visit counts.
- Mean rollout reward.
- Exploration statistics.
- Selection and backpropagation events.

For baseline agents:

- Render linear refinement chains.

For best-of-N:

- Render independent candidate branches from the root.

---

## 7. Historical Execution Replay

Implement an interactive replay system that reconstructs the search execution from recorded events.

This is one of the most important dashboard features.

### Playback Controls

Provide:

- Play.
- Pause.
- Step forward.
- Step backward.
- Jump to beginning.
- Jump to end.
- Adjustable playback speed.
- Timeline scrubbing.

Suggested speeds:

- 0.5×
- 1×
- 2×
- 4×

### Replay Semantics

The replay engine should process recorded events in logical execution order.

Examples:

1. Search run starts.
2. Root node appears.
3. Branch tasks are created.
4. Subagents begin working.
5. Candidate nodes appear.
6. Evaluations complete.
7. Rewards are recorded.
8. A frontier finishes.
9. Unsuccessful branches are pruned.
10. The next frontier begins.
11. A final candidate is selected.

The visualization must reflect recorded state transitions rather than the final state of every node.

For example, a node that was eventually pruned should initially appear as pending or evaluated and become pruned only when the corresponding pruning event occurs.

### Replay Time Model

Differentiate:

- Wall-clock timestamp.
- Logical event sequence.
- Frontier index.
- Candidate depth.

These are not interchangeable.

Use logical sequence numbers for deterministic reconstruction.

Use timestamps to show actual execution overlap and latency.

### Replay Engine

Build a pure TypeScript replay reducer:

```typescript
type ReplayState = {
  visibleNodeIds: Set<string>;
  nodeStates: Record<string, ReplayNodeState>;
  activeWorkers: Record<string, WorkerState>;
  selectedNodeId: string | null;
  completedFrontiers: number[];
  metrics: ReplayMetrics;
};

function applyEvent(
  state: ReplayState,
  event: SearchEvent
): ReplayState;
```

The reducer should be deterministic and independently unit-tested.

Do not directly mutate React Flow nodes as the sole source of replay state.

### Efficient Scrubbing

For long event sequences, implement periodic in-memory checkpoints.

Example:

- Save a replay state snapshot every 100 events.
- When seeking, restore the nearest prior snapshot.
- Replay only the remaining events.

Keep checkpoint intervals configurable.

Do not replay thousands of events from the beginning for every scrub operation.

### Missing or Inconsistent Events

If the logs are incomplete:

- Show a clear warning.
- Render the reliable portion of the trace.
- Avoid inferring unrecorded actions.
- Gracefully handle unknown event types.

Do not silently fabricate missing transitions.

---

## 8. Concurrent Subagent Timeline

Build a timeline inspired by distributed tracing tools.

Its purpose is to show how multiple subagents executed concurrently.

### Timeline Layout

Use a Gantt-style timeline with one lane per worker or branch task.

Example:

```text
Time ───────────────────────────────────────────────►

Agent A   [ Generate ][ Evaluate ][ Refine ][ Evaluate ]
Agent B   [ Generate ][ Evaluate ][ Refine ][ Evaluate ]
Agent C       [ Generate ][ Evaluate ]
Agent D                         [ Generate ][ Evaluate ]

Frontier 1   ──────────────────────────────────────
Frontier 2                                         ──
```

The actual interface should be interactive.

### Activity Types

Show:

- Queued.
- Candidate generation.
- LLM request.
- Code evaluation.
- Refinement.
- Idle.
- Completed.
- Failed.
- Canceled.

Use distinct visual treatments.

### Important Distinction

Subagents are execution workers, while search nodes represent candidate states.

The timeline must not assume a one-to-one mapping between workers and nodes.

A worker can produce multiple candidates.

A worker may also be reused across separate branch tasks.

### Timeline Interactions

Support:

- Hovering to view duration and metadata.
- Clicking an activity to select its associated node or task.
- Highlighting the corresponding search-tree branch.
- Filtering by worker.
- Filtering by frontier.
- Zooming the time axis.
- Displaying overlapping activity.

### Parallelism Metrics

Calculate from actual timestamps:

- Peak concurrent subagents.
- Average active subagents.
- Total worker busy time.
- Total worker idle time, where measurable.
- Frontier durations.
- Worker queue wait times.

Do not infer concurrency merely from the number of configured workers.

---

## 9. Node Inspector

Clicking any graph node should open a detailed inspector.

### General Information

Display:

- Node ID.
- Parent ID.
- Depth.
- Search frontier.
- Subagent task ID.
- Candidate strategy.
- Node lifecycle status.
- Evaluation reward.
- Creation and evaluation timestamps.

### Candidate Code

Provide a syntax-highlighted, read-only Python code viewer.

Support:

- Line numbers.
- Copy-to-clipboard.
- Expand to full-screen.
- Side-by-side comparison with parent candidate.

Prefer Monaco Editor or a lighter syntax-highlighting library if sufficient.

Do not enable editing or code execution from the dashboard.

### Candidate Comparison

For refinement nodes, display a diff against the parent candidate.

Highlight:

- Added lines.
- Removed lines.
- Modified lines.

This should make it easy to understand how test feedback changed the solution.

### Evaluation Results

Display:

- Passed tests.
- Failed tests.
- Runtime errors.
- Timeouts.
- Total execution time.
- Reward.

For failed tests, show:

- Test input.
- Expected output.
- Actual output.
- Standard error.
- Failure classification.

Use collapsible sections for long outputs.

Only display information actually preserved in the run artifacts.

### Reasoning History

Show the candidate's recorded strategy and explanation.

Display relevant ancestor candidate summaries and evaluation feedback.

Do not claim to reveal hidden model reasoning or private chain-of-thought content.

Use only explanations explicitly generated and recorded by BranchForge.

---

## 10. Analytics Dashboard

Add a separate analytics view within each run.

### Summary Metrics

Show:

- Total generated candidates.
- Evaluated candidates.
- Successful visible-test candidates.
- Pruned nodes.
- Maximum search depth.
- LLM calls.
- Input tokens.
- Output tokens.
- Total tokens.
- Total cost, if known.
- Wall-clock duration.
- Peak subagent concurrency.

### Required Charts

Implement the following:

**A. Best Reward Over Time**

Line chart showing the best visible-test reward observed as the search progresses.

Support event-index and elapsed-time axes.

**B. Cumulative Token Consumption**

Line chart showing token usage throughout the run.

Differentiate input and output tokens.

**C. Candidate Reward Distribution**

Histogram showing how candidate evaluation rewards are distributed.

**D. Candidate Status Breakdown**

Chart showing evaluated, failed, pruned, and successful candidates.

Avoid double counting overlapping status categories. Define whether this chart uses final lifecycle status or independent outcome categories.

**E. Subagent Activity**

Timeline or concurrency chart showing active workers over time.

**F. Frontier-Level Analysis**

For beam search, display:

- Frontier index.
- Number of candidates generated.
- Number evaluated.
- Number retained.
- Number pruned.
- Best reward.
- Frontier duration.

### Cost Reporting

Only display numeric API cost where valid pricing information was recorded.

If cost is unknown, show "Unknown".

Do not represent missing cost as zero.

---

## 11. Backend API

Create a lightweight FastAPI application integrated with the existing BranchForge package.

Use existing persistence models wherever possible.

### Required Endpoints

```http
GET /api/health

GET /api/runs
GET /api/runs/{run_id}

GET /api/runs/{run_id}/tree
GET /api/runs/{run_id}/events
GET /api/runs/{run_id}/metrics
GET /api/runs/{run_id}/timeline
```

### API Responsibilities

The backend should:

1. Discover saved runs under the configured runs directory.
2. Parse JSON and JSONL artifacts.
3. Validate run data.
4. Normalize data for frontend consumption.
5. Return structured errors.
6. Support pagination for run history.
7. Support event retrieval by sequence range where practical.
8. Avoid loading unnecessary large artifacts for list views.

### Security

Treat recorded candidate code and logs as untrusted text.

- Never execute candidate code.
- Never interpret stored content as HTML.
- Do not permit arbitrary filesystem paths from API parameters.
- Validate run IDs.
- Restrict file reads to the configured runs directory.
- Do not expose API credentials, environment secrets, or unrelated host files.
- Configure CORS only for the development frontend origin.
- Bind the development API to localhost by default.

Avoid introducing an authentication system for this local-first MVP.

### API Models

Create typed schemas for:

- RunSummary.
- RunDetail.
- SearchTreeResponse.
- SearchNodeResponse.
- SearchEventResponse.
- WorkerTimelineResponse.
- RunMetricsResponse.

Prefer stable, explicit response contracts.

If the existing BranchForge artifacts are inconsistent with the frontend's needs, implement a read-only adapter instead of modifying search behavior unnecessarily.

---

## 12. Event Data Compatibility

Before implementing replay, inspect the existing BranchForge event schema.

Determine whether recorded events contain enough information to reconstruct:

- Node creation.
- Candidate generation.
- Evaluation completion.
- Node status transitions.
- Branch assignments.
- Worker start and end times.
- LLM request boundaries.
- Frontier completion.
- Branch pruning.
- Final selection.

Do not assume every required event already exists.

### If Events Are Missing

Implement minimal additive instrumentation in the Python search runtime.

Preserve existing event types and serialized fields where possible.

Version the event schema if necessary.

Document new fields.

Do not rewrite search algorithms to accommodate the dashboard.

### Backward Compatibility

Older runs may not contain detailed worker timelines.

The dashboard should:

- Load their search trees where possible.
- Display supported metrics.
- Disable unavailable replay capabilities.
- Explain which data is missing.

Never fabricate historical worker activity.

---

## 13. Historical Replay vs. Live Monitoring

The MVP must fully support **historical replay of completed runs**.

Live monitoring is optional, but the architecture should permit adding it later.

Do not delay the project by implementing WebSocket streaming, distributed event buses, or complex synchronization infrastructure.

If implementing live updates is straightforward, use a lightweight polling or Server-Sent Events approach.

However:

- Historical replay takes priority.
- Live monitoring must not compromise deterministic replay.
- The UI should clearly distinguish recorded events from live activity.

---

## 14. Visual Design Requirements

Use a polished, dark developer-tool aesthetic.

### Suggested Design

- Dark charcoal background.
- Slightly lighter panels.
- Subtle borders.
- Restrained shadows.
- High-contrast readable text.
- Monospace typography for technical metadata.
- Clean sans-serif typography for UI labels.
- Semantic colors for search status.
- Minimal decorative animation.

### Interaction Quality

Include:

- Loading states.
- Empty states.
- Error states.
- Keyboard-accessible controls.
- Tooltips.
- Clear selected-node indication.
- Responsive panel sizing.
- Smooth zoom and pan.
- Sensible defaults for large search trees.

Do not overdecorate the UI with gradients or glassmorphism.

The visual hierarchy should prioritize the tree, selected node, and replay controls.

### Responsive Behavior

Desktop is the primary target.

For smaller screens:

- Collapse the run-history sidebar.
- Allow the node inspector to open as a drawer.
- Keep replay controls usable.
- Avoid permanently rendering three cramped columns.

---

## 15. Performance Requirements

Optimize for runs containing:

- Hundreds of search nodes.
- Thousands of recorded events.
- Several simultaneously active subagents.

Avoid unnecessary full graph relayouts.

Use memoized graph transformations when appropriate.

Throttle or debounce expensive layout recalculations.

Support incremental replay updates.

Virtualize large run-history tables if needed.

Avoid mounting heavy code viewers for every graph node.

Measure performance using a generated synthetic run containing at least:

- 500 nodes.
- 5,000 events.
- 8 simulated workers.

Synthetic data must be clearly labeled as test data and must not be presented as actual BranchForge results.

---

## 16. Proposed Project Structure

Inspect the existing repository before choosing exact paths.

A reasonable structure is:

```text
branchforge/
├── src/
│   └── branchforge/
│       ├── api/
│       │   ├── app.py
│       │   ├── routes/
│       │   │   └── runs.py
│       │   ├── schemas.py
│       │   └── services/
│       │       ├── run_reader.py
│       │       └── timeline_builder.py
│       └── ...
├── dashboard/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   ├── search-tree/
│   │   │   ├── timeline/
│   │   │   ├── inspector/
│   │   │   └── analytics/
│   │   ├── pages/
│   │   │   ├── RunsPage.tsx
│   │   │   └── RunDetailPage.tsx
│   │   ├── replay/
│   │   │   ├── reducer.ts
│   │   │   ├── engine.ts
│   │   │   └── checkpoints.ts
│   │   ├── hooks/
│   │   ├── types/
│   │   └── utils/
│   └── tests/
├── tests/
│   └── api/
└── runs/
```

Adapt this structure to match existing project conventions.

Avoid creating unnecessary abstraction layers.

---

## 17. Testing Requirements

Use Vitest and React Testing Library for frontend tests.

Use pytest for backend API tests.

### API Tests

Verify:

- Run listing.
- Run detail retrieval.
- Tree serialization.
- Event ordering.
- Metrics calculation.
- Invalid run IDs.
- Missing artifacts.
- Malformed JSONL events.
- Partial run compatibility.
- Filesystem path traversal prevention.

### Replay Engine Tests

Verify:

- Deterministic state reconstruction.
- Correct node appearance timing.
- Correct node-status transitions.
- Correct worker activity tracking.
- Correct frontier completion.
- Correct pruning behavior.
- Correct final selection.
- Backward stepping.
- Seeking.
- Checkpoint restoration.
- Missing event handling.

### Timeline Tests

Verify:

- Worker intervals are reconstructed correctly.
- Overlapping activity is displayed correctly.
- Tasks are associated with the correct workers.
- Multiple tasks can reuse a worker identity.
- Concurrency metrics are derived from timestamps.
- Missing start or end events are handled gracefully.

### Search Tree UI Tests

Verify:

- Nodes render correctly.
- Selecting a node opens its details.
- Parent paths can be highlighted.
- Pruned nodes are distinguishable.
- MCTS statistics render correctly.
- Collapsed subtrees behave correctly.

### End-to-End Tests

Use Playwright for browser-level tests if feasible.

Test:

1. Opening the dashboard.
2. Selecting a recorded run.
3. Viewing the search tree.
4. Selecting a candidate node.
5. Inspecting generated code.
6. Viewing test feedback.
7. Playing the replay.
8. Pausing and stepping backward.
9. Inspecting concurrent subagent activity.
10. Viewing analytics.

Use deterministic fixture data rather than requiring live LLM calls.

---

## 18. Implementation Plan

Implement the dashboard in phases.

### Phase 1 — Inspect Existing Artifacts

Review the existing BranchForge repository.

Identify:

- Search-tree models.
- Run persistence format.
- Event types.
- Worker metadata.
- Budget metrics.
- Current CLI behavior.

Document any schema gaps.

### Phase 2 — Backend API

Implement:

- FastAPI application.
- Run discovery.
- Run metadata endpoints.
- Tree endpoint.
- Event endpoint.
- Metrics endpoint.
- Timeline endpoint.

Write API tests.

### Phase 3 — Frontend Foundation

Initialize React, TypeScript, Vite, Tailwind, and shadcn/ui.

Implement:

- Application shell.
- Run history.
- Navigation.
- API client.
- Loading and error states.
- Dark theme.

### Phase 4 — Search Tree Visualization

Implement:

- React Flow canvas.
- Custom search nodes.
- Hierarchical layout.
- Node selection.
- Parent-path highlighting.
- Pruned-node visualization.
- Search-algorithm-specific metadata.

### Phase 5 — Node Inspector

Implement:

- Candidate details.
- Code viewer.
- Parent candidate diff.
- Evaluation feedback.
- Reasoning summaries.
- Search-node metadata.

### Phase 6 — Replay Engine

Implement:

- Typed event processing.
- Deterministic replay reducer.
- Playback controls.
- Timeline scrubbing.
- Replay checkpoints.
- Node lifecycle animations.

### Phase 7 — Subagent Timeline

Implement:

- Worker lanes.
- Task intervals.
- LLM requests.
- Code evaluations.
- Refinement intervals.
- Cross-highlighting with the tree.
- Parallelism statistics.

### Phase 8 — Analytics

Implement:

- Summary metric cards.
- Reward progression.
- Token consumption.
- Candidate reward distribution.
- Candidate status analysis.
- Frontier-level metrics.

### Phase 9 — Testing and Polish

Complete:

- API tests.
- Replay reducer tests.
- React component tests.
- Browser-level tests where feasible.
- Synthetic performance benchmark.
- Accessibility improvements.
- Documentation.
- Final validation.

---

## 19. Acceptance Criteria

The dashboard is complete when:

### Backend

- [ ] FastAPI loads existing BranchForge run artifacts.
- [ ] Run history is accessible through the API.
- [ ] Search trees are returned correctly.
- [ ] Event ordering is preserved.
- [ ] Metrics are calculated from recorded data.
- [ ] Worker timelines are reconstructed where supported.
- [ ] Missing and partial artifacts are handled gracefully.
- [ ] API file access is restricted to the runs directory.

### Frontend

- [ ] Users can browse recorded runs.
- [ ] Users can open a run by URL.
- [ ] Search trees render interactively.
- [ ] Nodes are selectable.
- [ ] Candidate code can be inspected.
- [ ] Parent-child code differences are visible.
- [ ] Test results can be inspected.
- [ ] Branches can be highlighted and collapsed.
- [ ] MCTS statistics display correctly.
- [ ] The interface supports dark mode.

### Replay

- [ ] Historical runs can be replayed.
- [ ] Playback can be paused.
- [ ] Users can step forward and backward.
- [ ] Users can scrub to arbitrary points.
- [ ] Playback speed is adjustable.
- [ ] Node states change according to recorded events.
- [ ] Replay is deterministic for identical event streams.
- [ ] Missing event data is clearly identified.

### Parallel Subagents

- [ ] Worker activity is visible on a timeline.
- [ ] Overlapping subagent execution is represented.
- [ ] Branch tasks are associated with search nodes.
- [ ] Refinement activity is visible.
- [ ] Worker failures and cancellations are distinguishable.
- [ ] Peak concurrent workers are calculated from actual events.

### Analytics

- [ ] Token consumption is displayed.
- [ ] Candidate rewards are visualized.
- [ ] Search depth is reported.
- [ ] Frontier-level statistics are available for beam search.
- [ ] MCTS statistics are available for MCTS runs.
- [ ] Unknown costs are displayed as unknown.
- [ ] Charts use real persisted data.

### Quality

- [ ] Frontend builds successfully.
- [ ] TypeScript type checking passes.
- [ ] Backend automated tests pass.
- [ ] Frontend automated tests pass.
- [ ] Browser-level tests pass where supported.
- [ ] No generated candidate code executes in the browser or API.
- [ ] README explains installation and usage.
- [ ] Synthetic performance fixture is available.

---

## 20. Development and Execution

Provide straightforward local development commands.

For example:

```bash id="w4k4ts"
# Start Python API
uv run uvicorn branchforge.api.app:app --reload --port 8000

# Start React dashboard
cd dashboard
npm install
npm run dev
```

Configure Vite to proxy `/api` requests to FastAPI during local development.

Avoid hardcoded production URLs.

Provide an example run or fixture so users can explore the dashboard immediately after installation, even without an LLM API key.

If existing BranchForge runs are available, the dashboard should discover them automatically.

---

## 21. Engineering Instructions for Astra

You are responsible for implementing this dashboard in the existing BranchForge repository.

Do not stop after creating a UI mockup or architecture document.

### Before Coding

1. Inspect the repository structure.
2. Identify existing data models and persistence formats.
3. Review event logs from actual runs where available.
4. Determine which replay and timeline features are supported by existing data.
5. Identify minimal instrumentation additions needed for missing events.

Do not assume the search engine already exposes all required metadata.

### During Implementation

- Keep the search engine's behavior unchanged.
- Prefer read-only API adapters.
- Make backend changes additive.
- Implement replay using actual recorded events.
- Keep frontend state deterministic and testable.
- Do not confuse worker identity with search-node identity.
- Do not fabricate intermediate execution states.
- Avoid excessive visual complexity.
- Run tests after each major implementation phase.
- Fix errors before moving to the next phase.

### Final Validation

Run:

1. Backend tests.
2. Frontend tests.
3. TypeScript type checks.
4. Frontend production build.
5. API integration tests.
6. Browser-level tests where feasible.
7. Replay using a recorded run.
8. Replay using the deterministic synthetic fixture.
9. Performance checks with 500 nodes and 5,000 events.

### Final Report

After implementation, provide:

- Summary of implemented functionality.
- Frontend and backend architecture.
- Any additions to BranchForge's event schema.
- Exact commands to start the dashboard.
- Exact commands to generate or load a demo run.
- Test results.
- Screenshots of the completed UI if supported.
- Known limitations.
- Features deferred to future iterations.

**The final product should be a polished, interactive observability dashboard that makes BranchForge's tree-search decisions, candidate refinements, parallel subagent activity, execution costs, and historical search progression understandable and inspectable.**