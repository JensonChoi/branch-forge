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
