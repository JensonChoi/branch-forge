import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

type Metric = {
  solved: number;
  trials: number;
  solve_rate: number;
  solve_ci95: number[];
  cost_per_solved: number | null;
  recovery_rate: number | null;
  recovery_opportunities: number;
};
type Summary = {
  stage: string;
  fixture: boolean;
  completed_trials: number;
  expected_trials: number;
  metrics: Record<string, Metric>;
};
type Trial = {
  problem_id: string;
  variant: string;
  run_id: string;
  grade: { passed: boolean | null; status: string };
};
async function read<T>(path: string): Promise<T> {
  const response = await fetch(`/api/experiments${path}`);
  if (!response.ok) throw Error("Unable to load experiments");
  return (await response.json()).data;
}
export function Experiments() {
  const [selected, setSelected] = useState("");
  const list = useQuery({
    queryKey: ["experiments"],
    queryFn: () => read<{ experiment_id: string; summary: Summary }[]>(""),
  });
  const detail = useQuery({
    queryKey: ["experiment", selected],
    queryFn: () => read<{ summary: Summary; trials: Trial[] }>(`/${selected}`),
    enabled: !!selected,
  });
  return (
    <section>
      <h1>Benchmark experiments</h1>
      {list.error && <p role="alert">{list.error.message}</p>}
      <select
        aria-label="Experiment"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
      >
        <option value="">Select an experiment</option>
        {list.data?.map((e) => (
          <option key={e.experiment_id} value={e.experiment_id}>
            {e.experiment_id} · {e.summary.stage}
          </option>
        ))}
      </select>
      {detail.error && <p role="alert">{detail.error.message}</p>}
      {detail.data && (
        <>
          <p>
            {detail.data.summary.fixture
              ? "Fixture data — not model performance"
              : "Real-model results"}{" "}
            · {detail.data.summary.completed_trials}/
            {detail.data.summary.expected_trials} trials
          </p>
          <table>
            <thead>
              <tr>
                <th>Algorithm</th>
                <th>Solved</th>
                <th>Rate / 95% CI</th>
                <th>Cost per solve</th>
                <th>Recovery</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(detail.data.summary.metrics).map(([name, m]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>
                    {m.solved}/{m.trials}
                  </td>
                  <td>
                    {(100 * m.solve_rate).toFixed(1)}% [
                    {m.solve_ci95.map((x) => (100 * x).toFixed(1)).join(", ")}]
                  </td>
                  <td>
                    {m.cost_per_solved == null
                      ? "Unknown / undefined"
                      : `$${m.cost_per_solved.toFixed(3)}`}
                  </td>
                  <td>
                    {m.recovery_rate == null
                      ? "N/A"
                      : `${(100 * m.recovery_rate).toFixed(1)}%`}{" "}
                    (n={m.recovery_opportunities})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2>Per-problem results</h2>
          <table>
            <thead>
              <tr>
                <th>Problem</th>
                <th>Algorithm</th>
                <th>Official result</th>
                <th>Replay</th>
              </tr>
            </thead>
            <tbody>
              {detail.data.trials.map((r, i) => (
                <tr key={i}>
                  <td>{r.problem_id}</td>
                  <td>{r.variant}</td>
                  <td>{r.grade.status}</td>
                  <td>
                    <a href={`/runs/${encodeURIComponent(r.run_id)}`}>
                      Open search tree
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
