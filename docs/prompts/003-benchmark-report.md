# BranchForge — LiveCodeBench Benchmark & Research Report

## 1. Project Objective

Extend the existing BranchForge repository with a rigorous, reproducible benchmarking framework using **LiveCodeBench and a real LLM**.

BranchForge is an agentic tree-search harness supporting single-trajectory agents, best-of-N sampling, sequential beam search, parallel-subagent beam search, and sequential MCTS.

It also includes an interactive React/TypeScript dashboard for visualizing search trees, replaying agent execution, inspecting candidate solutions, and analyzing subagent activity.

The objective of this milestone is to answer:

> Does explicit tree search improve the correctness, reliability, and inference efficiency of LLM coding agents compared with simpler generation and refinement strategies?

A secondary objective is to determine whether parallel-subagent execution reduces wall-clock latency without sacrificing solution quality or violating inference budgets.

The project must produce two major deliverables:

1. **A working LiveCodeBench integration** that can evaluate all existing BranchForge search strategies using the same real LLM, with reproducible experimental settings.
2. **A detailed research-style benchmark report** containing quantitative comparisons, statistical analysis, visualizations, failure analysis, and conclusions supported by actual experimental evidence.

Treat this as an empirical software engineering and inference-time scaling study.

Do not assume tree search will outperform simpler baselines.

Negative or inconclusive results are valid outcomes and must be reported accurately.

---

## 2. Existing Repository Integration

Before implementing anything, inspect the existing BranchForge repository.

Identify and reuse:

- Search algorithms and their configuration.
- Search orchestrator.
- Parallel subagent worker pool.
- LLM provider adapters.
- Coding environment.
- Docker sandbox.
- Search budget manager.
- Candidate and evaluation models.
- Run persistence.
- Event logs.
- Existing benchmark runner.
- FastAPI backend.
- React/TypeScript dashboard.

Do not rewrite working components unnecessarily.

Prefer additive changes and small, well-justified refactors.

The existing search algorithms must continue to work with their original example problems.

Use the existing CLI, configuration conventions, and persistence structures whenever possible.

---

## 3. Benchmark Selection

Use the official **LiveCodeBench code-generation benchmark**.

Official resources:

- Repository: https://github.com/LiveCodeBench/LiveCodeBench
- Code-generation dataset: https://huggingface.co/datasets/livecodebench/code_generation_lite
- Project website: https://livecodebench.github.io/

### Dataset Versioning

LiveCodeBench supports versioned datasets and date-window filtering.

Before implementation:

1. Inspect the official repository and current dataset documentation.
2. Identify the available stable releases.
3. Select and pin one release.
4. Record the exact dataset revision or commit.
5. Record the official evaluator revision.
6. Verify problem metadata and test formats.
7. Confirm compatibility with Python submissions.

Do not silently use a moving `latest` release for reproducible experiments.

Use the lightweight code-generation dataset where appropriate, but document whether the lite or full test suite was used.

### Problem Selection

The primary experiment should use **100 distinct problems**.

Select a stratified sample across:

- Difficulty levels.
- Problem sources, where available.
- Release dates.
- Algorithmic categories, if metadata supports them.

Use a fixed random seed.

Do not select problems based on whether BranchForge previously solved them.

If stratification metadata is missing, record the limitation and use the remaining available dimensions.

Save the exact selected problem IDs in a manifest.

### Contamination Considerations

Prefer problems published after the selected model's documented training cutoff when sufficiently many such problems are available.

Do not assume a recent model has not encountered benchmark problems.

Record:

- Problem publication dates.
- Model identifier and version.
- Known training-cutoff information, if available.
- Potential benchmark contamination limitations.

If an uncontaminated subset cannot be established, explicitly describe the benchmark as contamination-risk-aware rather than contamination-free.

---

## 4. Experiment Structure

Implement three experiment stages.

### Stage A — Integration Validation

Run 20 selected problems to verify:

- Dataset loading.
- Prompt formatting.
- Model API integration.
- Generated code extraction.
- Visible-test execution.
- Final candidate selection.
- Official benchmark grading.
- Budget accounting.
- Result persistence.
- Report generation.

This is a validation run, not the final research result.

Synthetic or fake-provider tests should be run before any real-model API calls.

### Stage B — Pilot Evaluation

Run 50 problems across all five search configurations with a real LLM.

Measure:

- Success rate.
- API cost.
- Token usage.
- Wall-clock latency.
- Candidate counts.
- Search failures.
- Infrastructure errors.

Use this stage to identify:

- Implementation defects.
- Excessive API costs.
- Model difficulty mismatch.
- Unreliable parsing.
- Weak benchmark coverage.
- Unnecessary search expansions.

After this stage, freeze the main experimental protocol.

### Stage C — Primary Evaluation

Run the 100-problem manifest using the frozen configuration.

Compare all five algorithms with matched resource budgets.

Use multiple independent trials where financially feasible.

Do not change the evaluation configuration after inspecting primary results unless explicitly beginning a separately labeled follow-up experiment.

The final report must distinguish pilot observations from primary experimental findings.

---

## 5. Algorithms to Compare

Evaluate five configurations:

### A. Single-Trajectory Agent

Generate one solution and iteratively refine it using visible-test feedback.

Do not explore independent branches.

Use this as the iterative-debugging baseline.

### B. Best-of-N Sampling

Generate multiple independent solutions to the same problem.

Candidates must not receive feedback from other candidates.

Evaluate them independently and select the strongest candidate using the same visible-test scoring criteria as the other algorithms.

### C. Sequential Beam Search

Use the existing BranchForge beam-search implementation.

- Multiple candidates per frontier.
- Evaluation-based ranking.
- Pruning.
- Feedback-guided refinement.
- One active branch worker at a time.

### D. Parallel-Subagent Beam Search

Use the same beam-search policy and configuration, but permit multiple independent subagents to explore branches concurrently.

Keep:

- Beam width.
- Branching factor.
- Local refinement limits.
- Evaluation rules.
- Budget limits.
- Selection logic.

Identical to the sequential beam configuration wherever possible.

Only the intended concurrency setting should differ.

### E. Sequential MCTS

Use the existing UCT-based MCTS implementation.

Include:

- Selection.
- Expansion.
- Objective evaluation.
- Reward backpropagation.
- Visit-count updates.
- Exploration/exploitation tradeoffs.

Keep MCTS simulations sequential.

### Experimental Interpretation

These configurations answer distinct questions.

| Comparison | Question |
|---|---|
| Single trajectory vs. best-of-N | Does generating independent alternatives help? |
| Best-of-N vs. beam | Does feedback-guided structured search help beyond additional sampling? |
| Sequential beam vs. parallel beam | Does concurrent execution reduce latency? |
| Beam vs. MCTS | Does adaptive node selection improve search efficiency? |
| All methods | Which produces the best accuracy-cost-latency tradeoff? |

Do not interpret parallel execution itself as a novel reasoning capability.

---

## 6. Real Model Integration

Use one configurable real LLM for the primary experiment.

Prefer a reasonably capable, moderately priced coding model.

Do not hardcode a specific vendor unless the repository already requires one.

### Configuration

Support settings such as:

```yaml
experiment:
  name: livecodebench_primary
  seed: 42

dataset:
  name: livecodebench
  scenario: codegeneration
  release: pinned_release
  sample_size: 100
  stratified: true

model:
  provider: configurable
  name: configurable
  temperature: 0.2
  max_output_tokens: 4096

execution:
  max_concurrent_containers: 4

report:
  enabled: true
  output_format:
    - markdown
    - html
```

Treat these values as initial examples.

Validate supported sampling parameters and output limits against the actual provider.

Use the same underlying model for every algorithm.

If the model exposes reasoning-effort controls, keep them fixed and record them.

Record the exact model identifier and provider-reported version where available.

### Real API Usage

Do not substitute the fake provider for the real-model benchmark.

The fake provider remains useful for deterministic tests.

The main benchmark must use genuine model API calls.

Handle:

- Rate limits.
- Transient provider failures.
- Request timeouts.
- Structured-output errors.
- Missing usage data.
- Unavailable pricing information.

Track retries separately from successful logical candidate generations.

Include retry overhead in actual cost and latency accounting.

---

## 7. Budget-Matched Evaluation

This is one of the most important requirements.

A search algorithm using more inference compute may achieve higher success merely because it receives more attempts.

Therefore, implement fair resource accounting and comparisons.

### Default Search Budget

Start with:

```yaml
budget:
  max_llm_calls: 8
  max_tokens: 30000
  max_wall_time_seconds: 180
  max_candidates: 8
```

These are starting parameters, not mandatory final values.

Keep the same limits across iterative search configurations for the main comparison.

For pure single-shot ability, also report an additional one-call baseline if the existing single-trajectory mode permits refinement.

### Budget Dimensions

Track:

- Logical LLM calls.
- Physical API requests, including retries.
- Input tokens.
- Output tokens.
- Reasoning tokens, where exposed.
- Total tokens.
- Actual dollar cost when known.
- Wall-clock duration.
- Candidate generations.
- Candidate evaluations.

Do not use LLM call count as the only measure of compute.

### Comparable Budgets

Provide analysis at:

- Matched call-count ceilings.
- Matched actual token consumption where feasible.
- Matched cost ceilings where prices are available.

Because algorithms may terminate early or use different numbers of tokens per call, do not claim exact budget matching merely because configurations share maximum limits.

Report actual resources consumed.

Do not make retrospective comparisons at equal realized cost without acknowledging early stopping and selection effects.

For cost-efficiency analysis, plot observed accuracy against cost and token use.

### Budget Enforcement

Reuse BranchForge's global and per-agent budget manager.

Verify that parallel workers cannot oversubscribe hard candidate or call-count budgets.

Record any overshoot or uncertainty for token and cost ceilings.

---

## 8. LiveCodeBench Adapter

Implement a benchmark-specific adapter without contaminating the generic search engine.

Suggested interface:

```python
class BenchmarkAdapter(Protocol):
    def load_problems(self) -> list[BenchmarkProblem]:
        ...

    def to_search_problem(
        self,
        problem: BenchmarkProblem,
    ) -> CodingProblem:
        ...

    def grade_final_solution(
        self,
        problem: BenchmarkProblem,
        code: str,
    ) -> FinalGrade:
        ...
```

The actual implementation may differ to preserve compatibility with existing code.

### Problem Conversion

LiveCodeBench includes problems with different input/output conventions.

Support both:

- Standard stdin/stdout programs.
- Function-based or method-based programming problems.

Adapt these formats without changing the intended problem semantics.

Use the official specification and checker as the source of truth.

Do not assume every problem can be executed as a standalone stdin/stdout script.

### Candidate Submission

Preserve the final code selected by each algorithm.

Do not accidentally submit every intermediate search candidate for final grading.

Each algorithm should produce one final selected solution per problem per trial.

### Official Grading

Use LiveCodeBench's official checker for final evaluation.

The official repository includes a custom evaluator that supports externally generated solutions with records containing `question_id` and `code_list`.

Verify the exact API and version before integration.

Do not implement a simplified replacement grader and treat its result as equivalent to the official benchmark.

If a compatibility wrapper is required, test it against known reference solutions.

---

## 9. Strict Evaluation Isolation

Search-time feedback and final benchmark grading must remain separate.

### Search-Time Evaluation

BranchForge may use:

- Public sample inputs and outputs.
- Explicitly permitted visible tests.
- Locally generated tests that do not reveal benchmark-private data.

Agents may use this feedback to revise candidates.

### Final Evaluation

After the algorithm selects one final candidate:

1. Freeze the selected code.
2. Submit it to the benchmark grading process.
3. Record whether it passes the official tests.
4. Persist the final result.
5. Do not expose grading feedback to the agent.

A failed final evaluation must not trigger further refinement within the same trial.

### Critical Isolation Requirements

Never expose private benchmark tests to:

- LLM prompts.
- Subagent contexts.
- Search evaluators.
- Intermediate candidate scoring.
- Search decision policies.
- Candidate selection logic.

Use a separate grading process or component that receives only the final candidate.

The official grader may have access to private tests, but the search runtime must not.

Treat previous experiment outcomes as potential leakage sources.

If the same model-agent configuration has already seen private-test diagnostics for a problem, exclude that contaminated run from the primary clean evaluation.

---

## 10. Experimental Metrics

Implement a structured metrics pipeline.

### Primary Metric: Final Correctness

Define:

\[
\text{Solve Rate} =
\frac{\text{Problems with a correct final submission}}
{\text{Total attempted problems}}
\]

A problem counts as solved only when the selected final solution passes the official benchmark evaluation.

Report this as end-to-end solve rate.

Do not label this measurement `pass@k`.

If reporting `pass@1`, clearly state that it refers to the first or single submitted candidate under the defined protocol. Do not conflate search-selected solutions with the standard pass@k independent-sampling estimator.

### Secondary Metrics

Measure:

- Visible-test success rate.
- Mean and median LLM calls.
- Mean and median tokens.
- Mean and median API cost.
- Mean and median latency.
- p95 latency.
- Candidates per problem.
- Candidate evaluation count.
- Maximum search depth.
- Average and peak worker concurrency.
- Frontier count.
- Branch pruning rate.
- API failure rate.

### Cost Efficiency

Measure:

\[
\text{Cost per Solved Problem} =
\frac{\text{Total API Spending}}
{\text{Number of Problems Solved}}
\]

Handle zero solved problems without dividing by zero.

Also report cost per attempted problem.

### Recovery Rate

BranchForge was motivated by the difficulty LLMs experience when correcting flawed reasoning.

Define a recovery opportunity as a problem where the first evaluated candidate failed visible tests.

Define recovery success as subsequently finding a correct final solution according to the official checker.

Measure:

\[
\text{Recovery Rate} =
\frac{\text{Recovery Opportunities Ending in Correct Solutions}}
{\text{Total Recovery Opportunities}}
\]

Report the denominator explicitly.

Also distinguish:

- First-attempt correctness.
- Visible-test repair success.
- Final official correctness after repair.

This metric is important for the project's central hypothesis.

---

## 11. Statistical Analysis

Implement statistical analysis rather than relying only on raw percentages.

### Confidence Intervals

Calculate 95% confidence intervals for solve rates.

Use a documented method, such as Wilson intervals, for individual proportions.

### Paired Comparisons

Every algorithm must evaluate the same problem manifest.

For two algorithms, compute the per-problem correctness difference.

Report:

- Absolute solve-rate difference.
- Relative difference where meaningful.
- Paired 95% confidence interval.
- Number of problems solved only by algorithm A.
- Number solved only by algorithm B.
- Number solved by both.
- Number solved by neither.

Use paired bootstrap resampling over problem IDs for difference intervals.

For a single trial per algorithm, McNemar's test may be used for paired binary correctness comparisons.

### Multiple Trials

When repeated trials are available, preserve the problem-level grouping.

Do not treat multiple trials of the same problem as independent new problems.

Use hierarchical or clustered resampling for uncertainty estimates.

### Cost and Latency

For cost and latency comparisons, report:

- Means.
- Medians.
- Percentiles.
- Paired differences.
- Confidence intervals where feasible.

Account for early termination and censored runs caused by budgets.

### Statistical Integrity

Avoid claiming statistical significance from small differences without adequate evidence.

Identify exploratory comparisons separately from pre-specified comparisons.

Do not select a favorable subset after inspecting results and present it as the original experiment.

---

## 12. Failure Analysis

Beyond aggregate scores, investigate how the search algorithms behave.

Create structured failure categories:

- Incorrect algorithm.
- Edge-case failure.
- Time-limit exceeded.
- Memory-limit exceeded.
- Runtime exception.
- Syntax or formatting error.
- Invalid model output.
- Search budget exhaustion.
- Premature pruning.
- Duplicate candidate generation.
- Failure to recover despite feedback.
- Provider or infrastructure failure.

Use objective runtime evidence where possible.

For conceptual categories such as "incorrect algorithm," label automatically inferred explanations as hypotheses unless supported by clear evidence or manual review.

### Case Studies

Select at least five informative problems after the primary evaluation.

Examples:

1. Single trajectory fails, but parallel beam succeeds.
2. Best-of-N succeeds, but tree search fails.
3. Beam succeeds, but MCTS fails.
4. MCTS succeeds, but beam fails.
5. Every algorithm fails.

For each case study, include:

- Problem identifier and difficulty.
- Relevant problem summary.
- Initial candidate strategy.
- Evaluation feedback.
- Search-tree structure.
- Refinements.
- Final selected solution.
- Final official grading outcome.
- Token usage.
- Cost.
- Latency.
- Interpretation.

Make the case studies accessible from the existing dashboard when possible.

Do not claim that the search tree proves the model's internal reasoning process. Analyze observable candidate generation, recorded explanations, actions, and feedback.

---

## 13. Report Generation

Build an automated reporting pipeline.

The report must be generated from saved benchmark data.

Do not hardcode outcome percentages or manually transcribe statistics.

### Required Outputs

Generate:

```text
reports/
  <experiment_id>/
    report.md
    report.html
    summary.json
    per_problem_results.csv
    configuration.json
    problem_manifest.json
    figures/
    case_studies/
```

Markdown is the canonical source.

HTML should be a polished, self-contained or locally viewable research-style report with embedded figures.

Optionally support PDF export, but do not make PDF generation a blocker if the existing environment lacks the required dependencies.

### Report Structure

Produce the following sections.

#### Title

**BranchForge: Evaluating Tree-Search-Based LLM Agents on LiveCodeBench**

Include:

- Experiment ID.
- Execution dates.
- Model.
- Benchmark version.
- Number of problems.
- Number of trials.
- BranchForge commit hash.

#### 1. Abstract

Write a concise abstract covering:

- Motivation.
- Experimental methods.
- Main findings.
- Performance tradeoffs.
- Limitations.

The abstract must be generated from actual results.

#### 2. Introduction

Explain:

- Why single-trajectory LLM agents can struggle with difficult coding problems.
- Why explicit search and feedback may help.
- Why parallel exploration is interesting.
- What BranchForge is designed to investigate.

Reference Tree of Thoughts and Language Agent Tree Search as related work.

Do not claim BranchForge invented tree search or agent-level search.

#### 3. Research Questions

Evaluate:

- RQ1: Does tree search improve correctness compared with single-trajectory and best-of-N baselines?
- RQ2: Does feedback-guided refinement improve recovery from initial failures?
- RQ3: Does parallel beam search reduce latency compared with sequential beam search?
- RQ4: Which algorithm offers the strongest correctness-cost tradeoff?
- RQ5: How do results vary by task difficulty?

#### 4. Methodology

Document:

- Dataset selection.
- Model configuration.
- Search algorithms.
- Budget limits.
- Visible-test policy.
- Official grading.
- Sampling parameters.
- Number of trials.
- Statistical methods.
- Experiment reproducibility.

#### 5. Results

Provide:

- Overall results table.
- Solve-rate comparison.
- Cost comparison.
- Latency comparison.
- Token usage.
- Recovery rates.
- Difficulty breakdown.
- Statistical confidence intervals.

#### 6. Search Behavior Analysis

Analyze:

- Search depths.
- Branch expansion patterns.
- Pruning.
- Refinement effectiveness.
- MCTS exploration behavior.
- Subagent concurrency.

#### 7. Case Studies

Include the selected individual problem analyses.

Link to corresponding BranchForge runs.

#### 8. Discussion

Explain:

- Where tree search helped.
- Where it failed.
- When extra compute was worthwhile.
- Whether MCTS improved over beam search.
- Whether parallelism improved latency.
- Whether results support the original hypotheses.

#### 9. Threats to Validity

Discuss:

- Benchmark contamination.
- Sample size.
- Task distribution.
- Model nondeterminism.
- Visible-test quality.
- Reward overfitting.
- Search configuration sensitivity.
- Provider pricing.
- Rate limits.
- Sandbox environment differences.
- Experimental run failures.

#### 10. Conclusion

Summarize findings and identify potential next experiments.

Do not exaggerate effect sizes or imply broad generalization from a single model or benchmark.

#### Appendix

Include:

- Full configuration.
- Selected problem IDs.
- Model information.
- Algorithm hyperparameters.
- Command-line instructions.
- Software revisions.
- Supplementary results.

---

## 14. Required Visualizations

Use Matplotlib, Plotly, or another appropriate visualization library.

Generate figures from actual results.

### Figure 1 — Final Solve Rate

Bar chart comparing all five algorithms.

Include 95% confidence intervals.

### Figure 2 — Accuracy vs. Cost

Scatter plot showing solve rate against average API cost per problem.

Label each algorithm.

### Figure 3 — Accuracy vs. Latency

Scatter plot showing solve rate against median latency.

### Figure 4 — Token Consumption

Compare input, output, and total tokens across algorithms.

### Figure 5 — Recovery Rate

Compare the rate of successful recovery after an initially failed candidate.

### Figure 6 — Difficulty Breakdown

Show solve rates by difficulty category.

Include sample counts.

### Figure 7 — Search Efficiency

Show final correctness or best visible-test reward against cumulative token usage where measurements support the analysis.

Do not substitute visible-test reward for official correctness without labeling the distinction.

### Figure 8 — Parallel Beam Speedup

Compare sequential and parallel beam latency.

Include:

- Median latency.
- p95 latency.
- Speedup distribution.
- Peak worker concurrency.

### Figure 9 — Per-Problem Outcomes

Heatmap showing which algorithms solved which problems.

Group or sort by difficulty.

### Figure 10 — Case Study Search Trees

Use saved BranchForge search-tree artifacts.

Generate static figures or link to dashboard replay pages.

---

## 15. Dashboard Integration

Extend the existing React/TypeScript dashboard rather than creating a separate application.

Add a **Benchmarks** section.

### Benchmark Overview

Display:

- Available experiments.
- Benchmark name.
- Dataset version.
- Model.
- Problem count.
- Trial count.
- Experiment status.
- Total API spending.
- Completion timestamp.

### Experiment Detail View

Show:

- Algorithm comparison table.
- Solve-rate chart.
- Accuracy-cost scatter plot.
- Latency comparison.
- Recovery statistics.
- Difficulty breakdown.
- Individual problem results.
- Links to the generated report.

### Drill-Down

Clicking a problem should show:

- Results by algorithm.
- Official grading outcome.
- Cost and latency.
- Linked search runs.

Users should be able to open existing tree-search replay views directly from the comparison page.

### Report Access

Provide links to:

- HTML report.
- Markdown report.
- CSV results.
- Figures.

Do not duplicate the entire reporting engine in TypeScript.

The Python benchmark pipeline should be the authoritative source for statistical calculations.

---

## 16. Experiment Persistence

Create a structured experiment directory.

```text
experiments/
  <experiment_id>/
    manifest.json
    config.json
    environment.json
    status.json

    runs/
      <algorithm>/
        <problem_id>/
          <trial_id>/
            result.json
            final_solution.py
            branchforge_run_id.txt

    grading/
      final_grades.jsonl

    aggregate/
      metrics.json
      per_problem.csv
      comparisons.json

    reports/
      report.md
      report.html
      figures/
```

Keep the experiment output compatible with BranchForge's existing run artifacts.

### Reproducibility Metadata

Save:

- Dataset release.
- Dataset commit or revision.
- Official grader revision.
- Exact problem manifest.
- Sampling seed.
- Model identifier.
- Model parameters.
- Search configurations.
- Token and cost budgets.
- Python version.
- Docker environment.
- Git commit hash.
- Experiment timestamps.

### Resumability

Experiments may be interrupted by API failures, rate limits, machine restarts, or user cancellation.

Implement checkpointing.

A resumed experiment should:

- Skip completed valid trials.
- Retry incomplete trials only under an explicit policy.
- Preserve previous results.
- Avoid double-counting.
- Maintain stable problem and trial identities.

Do not silently overwrite prior results.

---

## 17. CLI

Integrate benchmark commands into the existing BranchForge CLI.

Suggested commands:

```bash
branchforge benchmark lcb prepare \
  --config configs/benchmarks/livecodebench.yaml
```

```bash
branchforge benchmark lcb validate \
  --config configs/benchmarks/livecodebench.yaml
```

```bash
branchforge benchmark lcb run \
  --config configs/benchmarks/livecodebench.yaml \
  --stage pilot
```

```bash
branchforge benchmark lcb run \
  --config configs/benchmarks/livecodebench.yaml \
  --stage primary
```

```bash
branchforge benchmark lcb report \
  --experiment-id <experiment_id>
```

```bash
branchforge benchmark lcb inspect \
  --experiment-id <experiment_id>
```

Adapt these command structures to the existing CLI architecture where appropriate.

### Execution Safety and Cost Controls

The `prepare` command must not make paid model calls.

The `validate` command should perform local schema and infrastructure checks; if it includes real model calls, require an explicit option to enable them.

Before launching a paid batch, display:

- Selected model.
- Number of problems.
- Algorithms.
- Trials.
- Maximum logical LLM calls.
- Estimated cost range, if calculable.
- Configured spending limits.

Require explicit confirmation for substantial paid experiments unless an intentional noninteractive flag is supplied.

Never automatically launch the entire 100-problem evaluation merely because the feature was implemented.

The implementation should make the full run easy to start, but should not spend substantial API credits without explicit authorization.

---

## 18. Testing

Add automated tests for:

### Dataset Integration

- Dataset version loading.
- Stable problem selection.
- Stratified sampling.
- Deterministic manifest generation.
- Metadata parsing.
- Function-based problem adaptation.
- Stdin/stdout adaptation.
- Invalid problem handling.

### Official Grading

- Correct solution passes.
- Incorrect solution fails.
- Function-based solutions work.
- Timeouts are handled.
- Official checker errors are surfaced.
- Private test data never enters agent-visible state.
- Final selected code is frozen before official grading.

### Experimental Fairness

- Same problem IDs across algorithms.
- Same model configuration.
- Correct budget assignment.
- Correct trial identity.
- No accidental reuse of previous agents' feedback.
- No cross-algorithm leakage.
- Accurate accounting of retries.

### Statistics

- Correct solve-rate calculation.
- Correct paired difference calculation.
- Correct confidence intervals.
- Correct recovery-rate denominators.
- Correct handling of missing data.
- Correct zero-solve cost handling.
- Correct clustered resampling for repeated trials.

### Reporting

- Report generation from fixtures.
- Correct table calculations.
- Correct chart data.
- No fabricated metrics.
- Missing cost displayed as unknown.
- Report metadata matches experiment manifest.

### End-to-End

Use a deterministic fake provider to run a small full experiment:

1. Load benchmark-compatible problems.
2. Execute all five algorithms.
3. Collect final candidates.
4. Grade them.
5. Aggregate metrics.
6. Produce a report.
7. Load the experiment in the dashboard.
8. Navigate to a saved search-tree replay.

Automated tests must not require paid API usage.

---

## 19. Recommended Implementation Sequence

### Phase 1 — Repository and Benchmark Inspection

Inspect BranchForge and the official LiveCodeBench implementation.

Verify dataset schemas, grading interfaces, and compatibility gaps.

### Phase 2 — LiveCodeBench Adapter

Implement problem loading, selection manifests, prompt adaptation, submission formatting, and official grading integration.

### Phase 3 — Experiment Runner

Implement algorithm comparison, trial scheduling, resource accounting, resumability, and experiment persistence.

### Phase 4 — Metrics and Statistical Analysis

Implement correctness, cost, latency, recovery, paired comparisons, and confidence intervals.

### Phase 5 — Report Generator

Implement report templates, figures, tables, case studies, and HTML rendering.

### Phase 6 — Dashboard Integration

Add experiment browsing, algorithm comparisons, and links to detailed run replay.

### Phase 7 — Validation

Run unit tests, integration tests, official-grader compatibility tests, and deterministic full-pipeline tests.

### Phase 8 — Real Model Pilot

Once validated, run a small explicitly authorized real-model pilot.

Investigate failures and refine the experimental setup before the primary evaluation.

### Phase 9 — Primary Experiment

Execute the frozen 100-problem protocol when explicitly authorized.

Generate the final report from the recorded results.

---

## 20. Definition of Done

The milestone is complete when:

- [ ] LiveCodeBench code-generation problems load correctly.
- [ ] A stable dataset release is pinned.
- [ ] The 100-problem manifest is reproducible.
- [ ] All five algorithms are supported.
- [ ] At least one real LLM provider works.
- [ ] Search feedback and official grading are isolated.
- [ ] Both function-based and stdin/stdout problems are handled.
- [ ] Official benchmark grading is integrated.
- [ ] Global budgets and actual resource usage are recorded.
- [ ] Interrupted experiments can be resumed.
- [ ] Solve rates and secondary metrics are calculated.
- [ ] Statistical confidence intervals are generated.
- [ ] Recovery rates are calculated correctly.
- [ ] Cost and latency comparisons are available.
- [ ] The automated Markdown report is generated.
- [ ] A readable HTML report is generated.
- [ ] Figures and per-problem results are exported.
- [ ] The existing dashboard displays benchmark comparisons.
- [ ] Individual benchmark results link to search-tree replays.
- [ ] All deterministic tests pass.
- [ ] Actual real-model results are clearly distinguished from fixtures.
- [ ] The primary experiment can be launched explicitly with a controlled spending limit.

If the user has not authorized paid execution, completion means the pipeline is implemented and validated, not that the primary real-model experiment has already run.

---

## 21. Final Instructions for Astra

Implement this benchmark and reporting system in the existing BranchForge repository.

Do not merely produce a design proposal.

Start by inspecting the repository and the official benchmark interface.

Reuse existing functionality wherever possible.

Prioritize correctness, experimental validity, and reproducibility over feature count.

Do not fabricate results or report improvements that have not been measured.

Do not substitute visible-test success for official benchmark correctness.

Do not leak private evaluation tests into agent search contexts.

Do not modify search policies midway through the frozen primary experiment.

Do not launch expensive real-model experiments automatically.

### Required Final Response

After implementation, provide:

1. Summary of implemented functionality.
2. Files and modules created or modified.
3. Benchmark dataset and grader versions.
4. Exact configuration for the selected real model.
5. Commands to validate the integration.
6. Commands to run the pilot.
7. Commands to run the full primary benchmark.
8. Commands to generate the report.
9. Commands to view results in the dashboard.
10. Tests performed and their outcomes.
11. Any incomplete features.
12. Any real-model experiments actually executed, with actual costs and results.
13. Known limitations.

**The final deliverable must turn BranchForge into a reproducible experimental platform capable of evaluating inference-time tree search against strong baselines on LiveCodeBench and producing a rigorous, evidence-based research report.**