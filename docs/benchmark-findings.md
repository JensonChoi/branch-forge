# BranchForge: primary evaluation findings

## Main finding

This 50-problem experiment did not establish a conclusive correctness winner. Best-of-N and parallel beam had the highest observed solve rates, but the largest gap between methods was only two problems. Every paired 95% correctness interval included zero. This does not establish that the approaches are equivalent; the study may be too small to resolve modest differences.

## Experimental setup

- Benchmark: LiveCodeBench code generation lite, `release_v6`; 50 fixed, stratified problems, seed 42.
- Model: `gpt-5.4-mini-2026-03-17`, medium reasoning, strict JSON Schema, 25,000 completion tokens per request; temperature omitted.
- Five configurations, one trial per problem/configuration: 250 completed trials.
- Shared search ceilings: eight physical API requests, including retries, and eight candidates per trial; retries disabled. Search wall-time ceiling: 600 seconds.
- Search uses public samples; the frozen final candidate is graded separately by the official checker in Docker. Checker container memory: 1 GiB.
- **Baseline means single trajectory with sequential feedback-guided refinement**, not single-shot generation. It explores no independent branches.
- Dataset revision: `0fe84c3912ea0c4d4a78037083943e8f0c4dd505`. Official evaluator revision: `28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24`.

## Results

| Approach | Official solves | Solve rate | Mean search latency | Mean recorded tokens | Mean requests |
|---|---:|---:|---:|---:|---:|
| Single trajectory (baseline) | 44/50 | 88% | 33.6 s | 6,403 | 1.32 |
| Best-of-N | 45/50 | 90% | 63.5 s | 34,746 | 8.00 |
| Sequential beam | 43/50 | 86% | 67.9 s | 12,532 | 2.46 |
| Parallel beam | 45/50 | 90% | 42.5 s | 13,760 | 2.52 |
| Sequential MCTS | 44/50 | 88% | 35.4 s | 6,933 | 1.38 |

Across all configurations, 221 submissions passed, 26 were unsuccessful, and three had unknown official grades. Unknown grades count as unsolved in the end-to-end rates above. Search latency includes generation and visible-test evaluation, but excludes final private grading.

## Interpretation

### Correctness

- Best-of-N and parallel beam each solved 45 problems; baseline and MCTS each solved 44; sequential beam solved 43.
- Parallel beam improved over baseline by an observed 2 percentage points, with a paired 95% interval of **−4 to +10 percentage points**.
- MCTS and baseline had the same aggregate solve rate, with a paired difference interval of **−8 to +8 percentage points**.
- There is no convincing evidence here that structured tree search improves final correctness over single-trajectory refinement.

### Efficiency

- **Parallel beam versus sequential beam:** mean search latency was 37% lower. The paired mean reduction was 25.4 seconds, with an exploratory 95% bootstrap interval of 11.5–41.0 seconds. This is the clearest observed concurrency benefit.
- **Parallel beam versus Best-of-N:** the same solve count with 60% fewer recorded tokens and lower mean search latency. This suggests a more favorable observed resource tradeoff, without proving equal correctness.
- **Baseline:** a practical economical default for this setup. It solved only one fewer problem than the leaders while using substantially fewer recorded tokens. Early stopping reduced its average usage to 1.32 requests despite the eight-request ceiling.
- **MCTS:** no clear correctness or efficiency advantage over the baseline in this run.

### Recovery

The baseline and Best-of-N recovered on 2/4 initial visible-test failures each; parallel beam recovered on 2/6, sequential beam on 1/4, and MCTS on 1/4. These denominators are too small to support a reliable recovery ranking. Recovery means an initially failing visible candidate followed by a final official pass.

## Spending and execution

- Recorded returned-response API cost: **$14.13**.
- Conservative accounting, including unresolved reservations: **$15.04**.
- Seven requests have no returned usage, so exact total billing remains unknown. These figures are usage/accounting records, not invoice verification. Separate smoke and validation costs are excluded.
- Exact per-algorithm total costs are unavailable for four configurations because some usage is missing; token and latency comparisons are more complete but still have the limitations below.
- The run first stopped at 192 trials under the $12.86 cap. After explicit authorization to remove the cap, it resumed the remaining 58 trials without repeating completed results. The funding amendment and original artifacts were retained.

## Limits on the conclusions

- **Small sample and one repetition:** only 50 problems and one stochastic trial per method/problem. Confidence intervals remain wide; numerical ordering is not a reliable universal ranking.
- **Exploratory comparisons:** paired intervals use 2,000 problem-level bootstrap draws, seed 42, without multiple-comparison adjustment. Individual solve-rate intervals use Wilson intervals.
- **Missing grades and usage:** three grading memory-limit outcomes remain unknown. Unreturned request usage can understate recorded tokens and latency/cost comparisons may be affected by timeouts.
- **Unequal realized compute:** all methods share ceilings, but early stopping and different policies produce very different actual request/token usage. These are comparisons under common maximum budgets, not exactly matched realized compute.
- **Prior exposure and contamination risk:** the primary selection overlaps validation problems and protocol settings were tuned using validation observations. The dataset also predates the model's documented cutoff. This is contamination-risk-aware, not a clean untouched holdout.
- **Limited generality:** findings apply to this model, reasoning effort, benchmark subset, visible-test policy, and search configuration. They do not establish the best approach for other models or workloads.

## Practical takeaway

Use single trajectory as the economical reference implementation. If branching is desired, parallel beam has the most promising observed balance of correctness, recorded token usage, and latency. Treat an accuracy advantage for tree search as **unproven** by this study.

## Saved evidence

Summary statistics, the per-trial CSV, manifest, and cost receipt below are committed with this document. Full reports, event logs, and the detailed ledger remain local under ignored `runs/experiment-primary/`.

- [Full HTML report](../runs/experiment-primary/report.html)
- [Full Markdown report](../runs/experiment-primary/report.md)
- [Summary and paired statistics](benchmarks/primary/summary.json)
- [Portable per-trial results CSV](benchmarks/primary/per_problem_results.csv)
- [Cost accounting and artifact hashes](benchmarks/primary/evidence.json)
- [Spending ledger](../runs/experiment-primary/spending.json)
- [Final experiment manifest](benchmarks/primary/manifest.json)
- [Protocol and validation history](livecodebench.md)
