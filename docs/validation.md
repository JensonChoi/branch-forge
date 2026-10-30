# Local validation — 2026-10-29

Environment: Python 3.14.6 on macOS; Docker 29.9.2, aarch64; `python:3.12-slim` digest `sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159`.

The complete automated suite passes: 28 tests, including 12 Docker integration tests. Ruff checks, formatting checks, mypy, and package build pass. Python 3.12 is configured in GitHub Actions; local tests used the available Python 3.14 interpreter.

Docker checks cover five reference solutions against visible and hidden examples, wrong answers, syntax errors, runtime errors, timeout, OOM, output limits, non-root/read-only/no-secret execution, cancellation, and removal. Runtime tests cover branch isolation, synchronized concurrency, deterministic commits, sequential/parallel equivalence, reservations, failure isolation, deadlines, and persisted inspection.

The fake-provider beam demo `4f45abe89d734f4bb3d4187c1e4a206f` passed its visible tests with three concurrent workers, three concurrent model requests, and three concurrent containers. Its dynamic-programming branch improved from reward 0.5 to 1.0. `inspect` reconstructed its persisted tree successfully.

## Smoke benchmark

Command:

```sh
uv run branchforge benchmark --suite examples/benchmarks/smoke.yaml --algorithms baseline,best-of-n,beam,mcts --config configs/default.yaml
```

25 trials completed across five problems and five variants. Local artifacts: `runs/benchmark-34aefc125db44e56bd8702432cfb5ebf/` (ignored by Git).

| Variant | Held-out passes | Mean calls | Mean elapsed seconds | Maximum workers |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 0/5 | 29 | 0.557 | 1 |
| Best-of-N | 0/5 | 6 | 0.525 | 4 |
| Sequential beam | 5/5 | 8 | 1.141 | 1 |
| Parallel beam | 5/5 | 8 | 0.884 | 3 |
| MCTS | 0/5 | 30 | 0.506 | 1 |

These are scripted fixtures, not live LLM experiments. The fake provider deliberately supplies a correct reference only to the refining dynamic-programming branch. The rates therefore validate execution and reporting, not comparative algorithm quality. Duplicate caching also makes these timings unsuitable for claims about real-model latency. Some validation processes were concurrent; use isolated, repeated trials for performance research.

## Remaining limitations

- Live paid model requests have not been run. The LiteLLM adapter is implemented but live provider compatibility remains unvalidated.
- Provider-independent strict real-model token and dollar admission is not implemented. Unsupported hard ceilings are rejected explicitly; `configs/real.yaml` uses call/candidate/time bounds.
- No resumed execution, general-purpose environment implementation, or distributed runtime is included.
- Docker is practical isolation, not a complete defense against hostile workloads; see README.

## Search dashboard — 2026-10-29

Implemented on `feat/search-tree-dashboard`.

- `uv run pytest -q`: 35 passed, including available Docker integrations; no skips.
  Starlette emits a deprecation warning for its httpx-backed test client.
- `uv run ruff check src tests`, `uv run ruff format --check src tests`,
  `uv run mypy src`: passed.
- `uv build`: source and wheel distributions built successfully.
- `npm test` in `dashboard/`: 6 tests passed.
- `npm run typecheck` and `npm run build`: passed. Vite reports large chunks;
  Monaco is lazy-loaded and bundled locally, including its worker.
- `npm run test:e2e`: 2 browser tests passed locally, covering synthetic data,
  code inspection/diff, replay controls, timelines, analytics and a recorded run.
  The recorded-run test skips in a fresh checkout without v2 run artifacts.
- `npm install` after pinning the editor's DOMPurify override to 3.4.17:
  zero reported vulnerabilities.
- Actual fake-provider beam run `ac7843f0d5bd46698594a273f72df575` completed using
  Docker with visible reward 1.0, 8 candidates, 8 calls and 10,524 tokens.
- Chromium on this macOS development machine: 501 graph nodes (500 candidates
  and root) rendered in 732 ms; seeking through the 5,000-event fixture and
  rendering the end state took 132 ms. These are local observations, not portable
  latency guarantees. Eight simulated worker slots overlap in the fixture.
- Browser screenshots are generated at `dashboard/test-results/dashboard.png`
  and `dashboard/test-results/recorded-run.png` (ignored build artifacts).

Compatibility limits: detailed replay requires v2 event payloads. Older runs retain final
inspection and recorded task intervals. Incomplete intervals do not contribute fabricated
durations; idle time is unavailable. Live monitoring and hosted deployment remain out of scope.
