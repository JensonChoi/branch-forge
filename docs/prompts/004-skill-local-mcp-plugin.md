# BranchForge — Skills and Local MCP Plugin

## 1. Purpose and decision

Package BranchForge for use from Claude Code and Codex through **skills plus a local MCP server**. Make it possible to install the integration, configure the runtime, launch bounded searches conversationally, inspect results, and open the existing dashboard without working through repository development commands.

The selected architecture is:

```text
Claude Code / Codex
    │
    ├── Skills: onboarding, problem preparation, search, inspection, comparison
    │
    └── Local MCP server (stdio)
            │
            ├── Typed job API and lifecycle management
            ├── Existing BranchForge search engine and provider adapter
            ├── Existing Docker evaluation
            ├── Persisted run artifacts
            └── Packaged local dashboard
```

Keep one independent Python engine and one MCP implementation. Add small host-specific packaging adapters as necessary. Do not duplicate search algorithms in skills or platform wrappers.

This document records a future implementation request. Its creation does not authorize implementing the integration, installing plugins, publishing packages, or making paid model calls. Begin implementation only when the user explicitly requests it.

## 2. Product goal and intended experience

A user should be able to ask:

> Use BranchForge to explore solutions to this problem with beam search. Allow at most ten model calls, then show the best candidate and open the search dashboard.

The integration should:

1. Check the local runtime and identify actionable setup problems.
2. Convert the user's task into a supported, validated problem specification.
3. Explain the selected provider, model, algorithm, and actual enforced limits.
4. Start a search and promptly return a stable run ID.
5. Retrieve progress or cancel the job through explicit tools.
6. Return a concise result containing the selected candidate, visible reward, termination reason, usage, and a dashboard link.
7. Preserve artifacts for subsequent inspection after the conversation ends.

Users should not need a repository checkout, a Node development environment, or two manually managed web servers for normal operation. Docker and model-provider configuration remain runtime prerequisites where applicable; plugin installation must not imply they have already been installed or configured.

## 3. Scope and important boundaries

### Initial release

Support BranchForge's existing problem domain: generated Python stdin/stdout solutions evaluated against supplied visible tests. Support baseline, best-of-N, beam, and sequential MCTS through the existing engine.

Include:

- Local stdio MCP transport.
- Shared skills and host-specific plugin packaging.
- Setup diagnostics and a credential-free demo.
- Bounded asynchronous search jobs with status and cancellation.
- Read-only run/candidate inspection and comparison.
- One-command local dashboard serving using packaged frontend assets.
- Existing artifact compatibility and event-based historical replay.
- Local or team installation before public marketplace distribution.

### Deferred capabilities

Do not expand this milestone into:

- Arbitrary repository repair, multi-file patches, or general-purpose coding agents.
- Git worktree orchestration or configurable arbitrary shell evaluators.
- Delegating search branches to native Claude Code/Codex subagents.
- Automatically reusing host-session credentials, subscriptions, or model access.
- Remote execution services, hosted dashboards, authentication accounts, or billing.
- Distributed workers, parallel MCTS, training, or new search policies.
- Resuming interrupted search computation.
- An embedded MCP App UI; use the existing browser dashboard first.

The intended future audience remains a product decision: users solving test-defined problems versus developers modifying existing repositories. For this release, use the existing test-defined problem scope. Repository-level search requires a separate proposal covering isolated workspaces, patch candidates, and objective evaluators.

## 4. Ground the implementation in the repository

Before coding, inspect the current merged implementation and applicable repository instructions. Confirm:

- The CLI entry points, installation metadata, and build configuration.
- Search orchestration, worker interfaces, budgets, and cancellation semantics.
- Pydantic problem, candidate, evaluation, and tree models.
- Docker lifecycle, isolation, timeouts, and cleanup behavior.
- Provider integration and supported environment variables.
- JSON/JSONL persistence and current event schema.
- Dashboard API contracts and frontend production build output.
- Existing deterministic tests and Docker integration prerequisites.

At the time of this proposal, the package requires Python 3.12+, uses LiteLLM for real requests, and uses Docker for candidate execution. The dashboard uses FastAPI and a separately built React/Vite frontend. The current dashboard API is read-only and is not a search-job submission API or an MCP server.

Do not assume the package is already published, compiled dashboard assets are included in wheels, or host applications inherit credentials from an interactive shell. Inspect and validate each assumption.

## 5. Distribution and installation

Provide a versioned installation path for the Python runtime and thin plugin packages. Prefer a pinned package release invoked through an isolated Python tool runner when supported by the target host. Document a local source installation path for development before a public package release exists.

Requirements:

- Normal end-user installation must not require `npm install` or a Vite server.
- Produce frontend assets during release/build preparation and include them in the installed runtime distribution.
- Include a small supported demo problem and any resources needed outside a repository checkout.
- Resolve packaged resources using installation-safe mechanisms, not the current working directory.
- Store mutable run data and preferences outside installed plugin/package directories.
- Define and document a stable default data directory with an explicit override.
- Pin compatible runtime/plugin versions and provide an upgrade procedure.
- Clearly distinguish runtime installation, plugin registration, and provider credential setup.
- Do not perform automatic package publication or public-directory submission as part of implementation.

First target developer-machine use in Claude Code and local Codex surfaces. A web-hosted client cannot be assumed to execute a local stdio server or access Docker on the user's laptop.

## 6. Local MCP interface

Use a maintained MCP SDK and typed Pydantic inputs/outputs. Verify the SDK and each target host's supported protocol features at implementation time. Keep stdout exclusively for MCP protocol messages; route diagnostic logs to stderr.

Implement a small shared service layer that calls existing engine capabilities directly. Do not parse Rich terminal output or expose arbitrary shell execution as an MCP tool.

Suggested tool contract:

| Tool | Purpose |
| --- | --- |
| `check_environment` | Report runtime version, Docker/image availability, configured provider/model, credential presence, artifact-directory access, and dashboard availability |
| `start_search` | Validate a visible problem and bounded configuration, admit a job, and return its run ID and initial status promptly |
| `get_search_status` | Return lifecycle state, progress counters, termination reason, and available result summary |
| `cancel_search` | Request cancellation and report whether cleanup is pending or complete |
| `list_runs` | Paginate/filter saved run summaries |
| `get_run` | Return metadata, final selection, usage, compatibility warnings, and bounded result details |
| `get_candidate` | Return one candidate, ancestry references, and visible evaluation feedback |
| `compare_runs` | Compare selected run summaries with explicit problem/model/budget differences |
| `get_dashboard_url` | Start or reuse the local dashboard server as necessary and return a URL for the requested run |

These names describe intended capabilities; adapt naming to current host conventions without changing their meaning.

Interface requirements:

- Prefer an inline validated visible-problem object for submission. Avoid unrestricted filesystem paths in tool arguments.
- Accept an allowlisted set of configuration overrides, including algorithm, model/provider choice, call/candidate limits, timeout, and supported concurrency.
- Validate limits before starting work. Reject unsupported hard cost/token guarantees instead of silently ignoring them.
- Use run IDs as stable external handles, not caller-supplied arbitrary paths.
- Use explicit errors for invalid input, missing prerequisites, admission limits, unknown runs, and unavailable artifacts.
- Bound tool output. Do not return entire large trees, source collections, or event traces by default.
- Return an honest distinction between unknown usage/cost and measured zero.
- An optional idempotency key on submission must return the original job for an identical retry and reject reuse with different inputs.
- Annotate read-only versus state-changing tools accurately where the SDK supports it.

## 7. Job lifecycle and cancellation

Do not hold a single tool call open for the entire search. Use ordinary start/status/cancel tools as the portable baseline; host-specific background-task features are optional enhancements.

For the first release, the local MCP server owns its admitted search tasks. Default to one active search per server process; allow bounded configuration for additional concurrency. Reject excess admission clearly rather than creating an unbounded queue. Each search retains its existing internal worker, LLM, Docker, and budget limits.

Represent lifecycle states explicitly, for example `running`, `cancel_requested`, `completed`, `failed`, `canceled`, and `interrupted`. Report search termination reasons separately: exhausting a search or budget is not necessarily an infrastructure failure.

On cancellation:

- Request cancellation of the actual search task.
- Drain/clean up workers and containers through the existing runtime mechanisms.
- Preserve available artifacts and report partial results accurately.
- Do not report a completed cancellation before cleanup has finished.
- Make repeated cancellation safe, including for an already terminal run.

On normal MCP server shutdown or client disconnection, cancel owned work with bounded cleanup and preserve artifacts. Document this lifecycle explicitly. A first-release job is not guaranteed to survive its hosting MCP process.

On restart, retained artifacts must remain inspectable. Detect incomplete prior jobs and report them as interrupted; do not invent completion or automatically resume them. Isolate run directories and ownership across multiple client/server processes so one client cannot accidentally cancel another process's job. Report abrupt-process-death cleanup limitations honestly.

A durable background daemon may be considered later if users need searches to survive host application exit; do not introduce it implicitly in this milestone.

## 8. Skills and host packaging

Create focused skills for:

- **Setup:** diagnose prerequisites, guide configuration, and run a labeled fake-provider smoke test when requested.
- **Search:** collect the supported task and visible tests, choose an algorithm and bounded configuration, start the job, and report progress/results.
- **Inspect:** explain candidates, rewards, refinements, pruning, MCTS statistics, and recorded limitations; provide a dashboard link.
- **Compare:** compare runs while accounting for different problems, models, tests, budgets, and fake-versus-real providers.

Skill instructions must distinguish objective visible-test reward from general correctness. They must not promise that tree search improves quality without evidence. If the agent creates visible tests from a natural-language request, identify them as generated tests and explain what they cover before presenting the result as validated.

Keep search scheduling and enforcement in Python. Skills orchestrate tools and communicate results; they do not reproduce beam search or MCTS through prose instructions.

Share portable skill content and MCP code. Provide the appropriate current manifest/configuration for each host, testing installation separately. Do not assume one manifest file or local server command works unchanged on all clients.

Avoid lifecycle hooks unless a concrete requirement cannot be met with explicit tools. Public-directory restrictions and differing host trust behavior make hooks an unnecessary first-release dependency.

## 9. Provider credentials and usage

BranchForge continues to call its configured provider through its own adapter. Installing a plugin does not make the host conversation's model access available to BranchForge automatically.

- Require explicit fake/real provider selection and show the actual provider in diagnostics/results.
- Never infer real provider use from the model identifier alone; fake configurations may contain a real-looking model name.
- Resolve credentials through supported local environment/configuration mechanisms without embedding secret values in plugin manifests or tool inputs.
- Diagnose credential presence without printing values, hashing them into identifiers, or writing them into artifacts.
- Account for GUI apps having a different environment from shell sessions.
- Never pass provider credentials into candidate containers.
- Make real-run spending behavior clear using enforceable call/candidate/time limits. Do not claim a strict dollar ceiling when the engine does not support one.
- Use fake providers for automated validation; require explicit authorization for paid smoke tests.

Native host-agent generation, if pursued later, needs a separate adapter design for session isolation, cancellation, permission boundaries, and usage accounting. Do not extract host credentials or assume subscription access is interchangeable with API access.

## 10. Dashboard packaging and artifact access

Add one supported runtime entry point that serves the compiled dashboard and its existing read-only API from localhost. Keep the Vite workflow for contributors.

- Bind to loopback by default.
- Return the actual chosen port and URL; handle occupied ports without killing unrelated processes.
- Support direct navigation to a run URL and SPA reloads.
- Reuse an owned healthy dashboard process where practical and document its lifecycle.
- Open the browser through the host's supported action when requested; returning a URL must work without automatic browser launch.
- Keep artifacts confined to the configured data root, including symlink resolution.
- Do not turn the read-only browser API into an unauthenticated browser-accessible job-launch endpoint.
- Preserve legacy-run final inspection and explicit replay capability warnings.
- Reuse persisted event history instead of fabricating transitions for plugin-originated runs.

## 11. Security and architecture invariants

Preserve all repository constraints:

- Generated code executes only through the existing isolated evaluator, never on the host.
- Hidden tests remain outside search-worker inputs and search artifacts.
- Candidate code, logs, and model explanations are untrusted data, not tool instructions or HTML.
- Sibling histories remain isolated, beam commits deterministic, and MCTS sequential.
- MCP tools expose bounded domain operations, not arbitrary host commands.
- No credentials are committed, exposed through tool responses, or mounted into containers.
- Setup must report missing Docker or permissions rather than weaken isolation to make a demo work.

## 12. Implementation sequence when authorized

1. Audit current interfaces and verify official plugin/MCP guidance for both hosts.
2. Extract or introduce the minimum shared application service needed by CLI and MCP without changing algorithm semantics.
3. Add structured job admission, status, cancellation, ownership, and shutdown handling.
4. Add and protocol-test the local stdio MCP server.
5. Package dashboard assets and installation-safe demo resources; implement local serving and environment checks.
6. Add shared workflow skills and host-specific plugin manifests/setup documentation.
7. Test installation and a complete fake-provider workflow in both host applications.
8. Validate built distributions from outside the repository; document limitations and release procedures.

Do not publish a package or marketplace listing merely to claim completion. Local installation evidence is sufficient for the first milestone; publication is a separate authorized action.

## 13. Tests and acceptance criteria

### Engine and service

- Existing search tests remain green, including deterministic beam behavior and sequential MCTS.
- A search started through the service has the same algorithm/evaluation semantics as the equivalent CLI run.
- Start returns promptly; progress, terminal status, partial artifacts, and final selection are consistent.
- Admission is bounded; duplicate idempotent submission does not create duplicate provider charges.
- Cancellation is tested while queued for an internal resource, during generation, and during evaluation.
- Server shutdown cleans up owned tasks; restart identifies interrupted jobs without fabricated results.
- Multiple clients/processes do not share cancellation ownership accidentally.

### MCP

- Use a real MCP client over stdio to test initialization, tool discovery, argument validation, errors, status polling, and cancellation.
- Verify that stdout contains no Rich output or diagnostic noise.
- Test missing credentials, Docker unavailable, missing image, invalid configuration, unknown run, malformed artifacts, and unsafe paths.
- Confirm tool responses do not expose secrets, hidden tests, or unbounded event/code payloads.
- Fake-provider tests require no paid API calls. Docker skips must be reported explicitly.

### Packaging and dashboard

- Build source and wheel distributions and verify inclusion of frontend assets and demo resources.
- Install the built artifact into a clean environment and exercise it from a directory unrelated to the repository.
- End-user use requires no Node runtime or frontend build step.
- Dashboard URLs work, direct run reloads work, and port conflicts preserve unrelated services.
- Saved runs remain accessible after restarting the MCP integration.

### Host acceptance

For both Claude Code and Codex, record evidence that a user can:

1. Install/load the local plugin using documented steps.
2. Run setup and receive actionable prerequisite diagnostics.
3. Start a supported problem with a fake provider and explicit limits.
4. Poll and cancel a longer deterministic test run.
5. Inspect candidate code, visible test feedback, final selection, and usage.
6. Open the packaged dashboard and replay a completed v2 run.
7. Return in a later conversation and inspect saved artifacts.

If a host is unavailable, distinguish protocol/packaging validation from actual host acceptance. Do not claim both platforms have been tested based only on shared MCP tests.

Run the repository's Python lint, formatting check, type checks, tests, and build, plus frontend unit/type/build/browser checks affected by dashboard packaging. Add targeted lifecycle and installation tests rather than requiring paid model access.

## 14. Final implementation report

Provide:

- Architecture and exact shared-versus-host-specific boundaries.
- Exact runtime installation and plugin registration steps for both hosts.
- Credential setup guidance and fake/real provider behavior.
- Tool contracts, enforced limits, lifecycle behavior, and cancellation guarantees.
- Commands for a credential-free demo and packaged dashboard launch.
- Test results, explicitly noting Docker and host-specific skips.
- Screenshots or transcript excerpts demonstrating the supported installation/search/inspection flow.
- Known limitations and features deferred to later milestones.
- Package/public-directory publication status without implying an unpublished artifact is installable from a public registry.

## 15. Research references and freshness

The feasibility assessment used the following official documentation, reviewed during the October 2026 discussion. Revalidate these pages when implementation begins; manifests, transport support, distribution rules, and host availability can change.

- OpenAI plugin packaging: https://developers.openai.com/plugins/build/plugins
- OpenAI plugin architecture: https://developers.openai.com/plugins/concepts/plugins
- OpenAI desktop-only submission: https://developers.openai.com/plugins/deploy/desktop-only
- Claude Code plugin overview: https://code.claude.com/docs/en/plugins
- Claude Code MCP integration: https://code.claude.com/docs/en/mcp

At review time, OpenAI documented a portable root plugin manifest with Codex compatibility support, while Claude Code documented its own plugin manifest and bundled skills/MCP components. OpenAI's desktop-only submission guidance also described an allowlisting requirement for local MCP submissions. These are distribution considerations to verify, not reasons to block local development or team installation.
