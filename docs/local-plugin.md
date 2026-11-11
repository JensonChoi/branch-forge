# Local skills and MCP integration

BranchForge's Python engine remains the only search implementation. The CLI and local
job service share search construction; MCP adds typed start/status/cancel operations.
The dashboard remains read-only. Four portable skills are copied into thin Codex and
Claude Code packages by release preparation. Runtime and plugin version is 0.1.0;
the plugin command rejects a mismatched runtime.

## Build and install

For contributors, from the source checkout:

```sh
uv sync --locked
python scripts/prepare_release.py
uv build
```

Release preparation requires Node/npm, builds the dashboard, and assembles plugin
skills. Wheels and source distributions contain compiled assets and the demo;
ordinary users do not need Node or a checkout. Missing assets fail distribution builds.
Give users the wheel and the `plugins/` directory together. Nothing has been published.

Install the supplied wheel in an isolated tool environment (use its actual absolute path):

```sh
uv tool install /absolute/path/branchforge-0.1.0-py3-none-any.whl
branchforge demo
branchforge dashboard
```

Docker must be running with `python:3.12-slim` available (`docker pull python:3.12-slim`).
The demo uses a fake provider but evaluates code in Docker. No candidate code runs on
its host. `branchforge mcp` is the stdio entry point; its stdout is protocol-only.
If a GUI host cannot find `branchforge`, replace the manifest command with the absolute
path printed by `command -v branchforge`; do not embed credentials.

For Codex CLI, using the supplied plugins directory:

```sh
codex plugin marketplace add /absolute/path/plugins
codex plugin add branchforge@branchforge-local
```

For Claude Code:

```sh
claude --plugin-dir /absolute/path/plugins/claude
```

Start a new conversation and ask to use BranchForge setup. Install/load registration
is separate from runtime installation and provider configuration. For upgrades,
install the matching new wheel with `uv tool install --force /path/to/new.whl`, replace
the plugin bundle, refresh/reinstall its registration, and restart its MCP process.
Do not upgrade while searches are running.

Packaging follows [OpenAI's portable plugin guide](https://developers.openai.com/plugins/build/plugins)
and [Claude Code's manifest reference](https://code.claude.com/docs/en/plugins-reference).
Local stdio requires a local host; web-hosted clients cannot execute this runtime.

## Tools and bounds

- `check_environment`: Docker/image, credential presence, storage and UI diagnostics.
- `start_search`: inline visible problem, explicit `fake`/`real`, model, algorithm,
  call/candidate/time/concurrency bounds, optional idempotency key.
- `get_search_status`, `cancel_search`: poll lifecycle and request owned-job cleanup.
- `list_runs`, `get_run`: paginated summaries and selected candidate node references.
- `get_candidate`: JSON text slices containing code, ancestry and visible feedback;
  use offset and total_chars to retrieve subsequent slices.
- `compare_runs`: two to ten summaries with problem/test fingerprints, provider and limits.
- `get_dashboard_url`: start/reuse owned loopback UI, returning the actual port and run URL.

Search defaults: beam, 10 physical model calls, 10 candidates, 300 seconds, four workers
(one for baseline/MCTS). Submission caps: 10,000 calls/candidates, 86,400 seconds,
32 workers, 12,000 serialized problem characters. Lists default to 20 and cap at 100;
candidate slices default to 8,000 characters and cap at 16,000. Unsupported fields,
hidden tests, paths, token ceilings and dollar ceilings are rejected. Unknown cost
remains null. Visible test reward is not a general correctness guarantee.

Real requests use LiteLLM with explicitly supplied model names. Supported credential
presence checks cover OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY and AZURE_API_KEY;
other provider mechanisms report unknown presence. Set secrets in the host process's
environment, never tool arguments or manifests. GUI processes may not inherit shell
exports. No host conversation credentials/subscriptions are reused. Real searches
spend money and require authorization; validation uses fake providers only.

## Persistence and lifecycle

Integration data defaults to `~/.local/share/branchforge`; override with
`BRANCHFORGE_DATA_DIR` or `--data-dir`. Existing `solve` defaults remain unchanged;
point the dashboard at an older runs directory to inspect it.

The MCP process owns at most one active search by default (`--max-active 1..32`).
Excess admission is rejected; there is no job queue. Run IDs are stable; idempotency
keys persist across servers and identical retries return the same job. Changed inputs
with the same key fail. OS file locks distinguish active owners from dead processes.
Other processes may inspect but cannot cancel owned work.

States are running, cancel_requested, completed, failed, canceled and interrupted.
Budget exhaustion is a normal completion reason. Cancellation targets the real task;
`canceled` is reported only after its cleanup scope finishes. Shutdown requests
cancellation and waits up to 30 seconds. Abrupt termination or cleanup exceeding that
window can leave Docker resources requiring manual inspection. Unfinished runs become
interrupted when their owner is gone; computation is never resumed automatically.

The UI binds to 127.0.0.1, chooses a free port when the requested port is occupied,
and stops with its MCP owner. URLs do not automatically launch a browser. Legacy
artifacts retain final inspection and explicit replay warnings. Artifact paths are
resolved and confined to the selected root.

## Validation evidence

See the integration section in `validation.md`. Protocol tests are distinct from
full host conversation acceptance. Claude Code was unavailable in this environment;
Codex local installation was tested in an isolated temporary profile. No package,
marketplace listing, paid provider smoke test, or production host configuration was
published or changed.
