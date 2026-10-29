import React, { useState, useMemo, useEffect, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type ReactFlowInstance,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts";
import {
  GitBranch,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Replay, type Event, type SearchNode } from "./replay";
import "@xyflow/react/dist/style.css";
import "./style.css";
const DiffEditor = lazy(() => import("./CodeDiff"));
const CodeEditor = lazy(() =>
  import("./CodeDiff").then((m) => ({ default: m.Editor })),
);
import { Button } from "./components/ui/button";
type Envelope<T> = { data: T; warnings: string[] };
type Run = {
  run_id: string;
  title: string;
  algorithm: string;
  status: string;
  model: string;
  visible_reward: number | null;
  selected_node_id: string | null;
  detailed_replay: boolean;
  budget: Record<string, number | null>;
};
type Interval = {
  frontier_index: number | null;
  task_id: string;
  worker_id: string;
  kind: string;
  start: string;
  end: string | null;
  candidate_id?: string;
  outcome?: string;
};
async function get<T>(path: string): Promise<Envelope<T>> {
  const r = await fetch("/api/" + path);
  if (!r.ok) throw Error(`Unable to load ${path}: ${r.status}`);
  return r.json();
}
function useApi<T>(path: string) {
  return useQuery({ queryKey: [path], queryFn: () => get<T>(path) });
}
function App() {
  const [id, setId] = useState(location.pathname.split("/")[2] ?? "");
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState("title");
  const [offset, setOffset] = useState(0);
  const runs = useApi<{ items: Run[]; total: number }>(
    `runs?limit=100&offset=${offset}`,
  );
  useEffect(() => {
    const listener = () => setId(location.pathname.split("/")[2] ?? "");
    addEventListener("popstate", listener);
    return () => removeEventListener("popstate", listener);
  }, []);
  return (
    <>
      <header>
        <GitBranch />
        <strong>BranchForge</strong>
        <span className="muted">SEARCH EXECUTION DEBUGGER</span>
        <span className="local">● Local artifacts</span>
      </header>
      <div className="shell">
        <aside>
          <h2>Run history</h2>
          <select
            aria-label="Sort runs"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="title">Problem title</option>
            <option value="algorithm">Algorithm</option>
            <option value="reward">Visible reward</option>
          </select>
          <div>
            <Button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 100))}
            >
              Previous
            </Button>
            <Button
              disabled={offset + 100 >= (runs.data?.data.total ?? 0)}
              onClick={() => setOffset(offset + 100)}
            >
              Next
            </Button>
          </div>
          <input
            aria-label="Filter runs"
            placeholder="Search runs or algorithms…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {runs.error && <p role="alert">{runs.error.message}</p>}
          {runs.isLoading && <p>Loading runs…</p>}
          {runs.data?.data.items
            .slice()
            .sort((a, b) =>
              sort === "reward"
                ? (b.visible_reward ?? -1) - (a.visible_reward ?? -1)
                : String(a[sort as "title" | "algorithm"]).localeCompare(
                    String(b[sort as "title" | "algorithm"]),
                  ),
            )
            .filter((r) =>
              `${r.title} ${r.algorithm} ${r.run_id}`
                .toLowerCase()
                .includes(filter.toLowerCase()),
            )
            .map((r) => (
              <Button
                className={"run " + (id === r.run_id ? "active" : "")}
                key={r.run_id}
                onClick={() => {
                  history.pushState({}, "", `/runs/${r.run_id}`);
                  setId(r.run_id);
                }}
              >
                <b>{r.title}</b>
                <span>
                  {r.algorithm ?? "Unknown"} · {r.status}
                </span>
                <code>{r.run_id.slice(0, 12)}</code>
                <span>
                  reward {r.visible_reward ?? "—"} ·{" "}
                  {r.budget.total_tokens ?? "—"} tokens
                </span>
              </Button>
            ))}
          {runs.data?.data.total === 0 && (
            <p>No runs yet. Generate a fake-provider demo to begin.</p>
          )}
        </aside>
        <main>
          {id ? (
            <RunView key={id} id={id} />
          ) : (
            <div className="welcome">
              <GitBranch size={48} />
              <h1>Follow the search.</h1>
              <p>
                Select a recorded run to inspect candidates, replay decisions,
                and explore worker activity.
              </p>
            </div>
          )}
        </main>
      </div>
    </>
  );
}
function RunView({ id }: { id: string }) {
  const [frontier, setFrontier] = useState("");
  const [axis, setAxis] = useState("sequence");
  const [flow, setFlow] = useState<ReactFlowInstance | null>(null);
  const detail = useApi<Run>(`runs/${id}`),
    tree = useApi<{ nodes: Record<string, SearchNode> }>(`runs/${id}/tree`),
    events = useApi<Event[]>(`runs/${id}/events`),
    timeline = useApi<{
      intervals: Interval[];
      peak_concurrency: number | null;
    }>(`runs/${id}/timeline`),
    metrics = useApi<Record<string, unknown>>(`runs/${id}/metrics`);
  const [selected, setSelected] = useState<string | null>(null),
    [cursor, setCursor] = useState(0),
    [replaying, setReplaying] = useState(false),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [direction, setDirection] = useState("LR"),
    [collapsed, setCollapsed] = useState<Set<string>>(new Set()),
    [tab, setTab] = useState("tree"),
    [diff, setDiff] = useState(false),
    [worker, setWorker] = useState(""),
    [zoom, setZoom] = useState(1);
  const trace = events.data?.data ?? [];
  const engine = useMemo(() => new Replay(trace), [events.data]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(
      () =>
        setCursor((c) => {
          if (c >= trace.length) {
            setPlaying(false);
            return c;
          }
          return c + 1;
        }),
      600 / speed,
    );
    return () => clearInterval(timer);
  }, [playing, speed, trace.length]);
  const state = useMemo(() => engine.seek(cursor), [engine, cursor]);
  const all = tree.data?.data.nodes ?? {};
  const nodes = replaying ? state.nodes : all;
  const final = replaying ? state.selected : detail.data?.data.selected_node_id;
  const positions = useMemo(() => {
    const g = new dagre.graphlib.Graph()
      .setGraph({ rankdir: direction, nodesep: 35, ranksep: 65 })
      .setDefaultEdgeLabel(() => ({}));
    Object.values(all).forEach((n) =>
      g.setNode(n.node_id, { width: 215, height: 105 }),
    );
    Object.values(all).forEach((n) => {
      if (n.parent_id && all[n.parent_id]) g.setEdge(n.parent_id, n.node_id);
    });
    dagre.layout(g);
    return g;
  }, [tree.data, direction]);
  useEffect(() => {
    if (selected && flow) {
      const p = positions.node(selected);
      if (p) void flow.setCenter(p.x, p.y, { zoom: 0.85, duration: 250 });
    }
  }, [selected, flow, positions]);
  const ancestors = new Set<string>();
  let a = selected ? nodes[selected] : undefined;
  while (a && !ancestors.has(a.node_id)) {
    ancestors.add(a.node_id);
    a = nodes[a.parent_id ?? ""];
  }
  const visible = Object.values(nodes).filter((n) => {
    let p = n.parent_id;
    const seen = new Set<string>();
    while (p && !seen.has(p)) {
      seen.add(p);
      if (collapsed.has(p)) return false;
      p = nodes[p]?.parent_id ?? null;
    }
    return true;
  });
  const graph: Node[] = visible.map((n) => ({
    id: n.node_id,
    position: {
      x: (positions.node(n.node_id)?.x ?? 0) - 107,
      y: (positions.node(n.node_id)?.y ?? 0) - 52,
    },
    data: {
      label: (
        <>
          <small>{n.node_id}</small>
          <b>{n.candidate?.strategy ?? "Search root"}</b>
          <span>
            {n.status} {n.provisional ? "· provisional" : ""}
          </span>
          <span>
            depth {n.depth} · reward {n.evaluation?.reward ?? "—"}{" "}
            {final === n.node_id ? "★ selected" : ""}
          </span>
        </>
      ),
    },
    className: `search-node ${n.status.toLowerCase()} ${ancestors.has(n.node_id) ? "ancestor" : ""} ${final === n.node_id ? "final" : ""}`,
  }));
  const n = selected ? nodes[selected] : undefined;
  const warnings = [
    ...new Set([
      ...(detail.data?.warnings ?? []),
      ...(tree.data?.warnings ?? []),
      ...(events.data?.warnings ?? []),
    ]),
  ];
  const chart = useMemo(() => {
    let best = 0,
      input = 0,
      output = 0;
    return trace.map((e) => {
      if (e.event_type === "CANDIDATE_EVALUATED")
        best = Math.max(best, e.reward ?? 0);
      if (e.event_type === "LLM_FINISHED") {
        input += e.input_tokens ?? 0;
        output += e.output_tokens ?? 0;
      }
      return {
        sequence: e.sequence,
        elapsed:
          (Date.parse(e.timestamp) - Date.parse(trace[0]?.timestamp)) / 1000,
        best,
        input,
        output,
      };
    });
  }, [events.data]);
  if (detail.error || tree.error || events.error)
    return (
      <p role="alert">
        Could not load run. Check API availability and run artifacts.
      </p>
    );
  return (
    <>
      <div className="title">
        <div>
          <small>
            {detail.data?.data.algorithm ?? "SEARCH RUN"} / {id.slice(0, 12)}
          </small>
          <h1>{detail.data?.data.title ?? "Loading…"}</h1>
        </div>
        <span className="badge">{detail.data?.data.status}</span>
      </div>
      {warnings.length > 0 && (
        <details className="warning">
          <summary>{warnings.length} artifact compatibility notes</summary>
          {warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </details>
      )}
      <nav>
        {["tree", "timeline", "analytics"].map((t) => (
          <Button
            className={tab === t ? "active" : ""}
            key={t}
            onClick={() => setTab(t)}
          >
            {t}
          </Button>
        ))}
        <Button
          onClick={() => {
            setReplaying(false);
            setPlaying(false);
          }}
        >
          Final snapshot
        </Button>
        <span className="muted">
          {replaying ? `Replay · event ${cursor}` : "Recorded final state"}
        </span>
      </nav>
      {tab === "tree" && (
        <div className="workspace">
          <section className="canvas">
            <div className="canvas-tools">
              <select
                aria-label="Select candidate"
                value={selected ?? ""}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Select candidate…</option>
                {Object.values(nodes).map((n) => (
                  <option key={n.node_id} value={n.node_id}>
                    {n.candidate?.strategy ?? n.node_id}
                  </option>
                ))}
              </select>
              <Button
                onClick={() => setDirection(direction === "LR" ? "TB" : "LR")}
              >
                Layout: {direction}
              </Button>
              <Button
                disabled={!selected}
                onClick={() =>
                  setCollapsed((old) => {
                    const next = new Set(old);
                    if (selected) {
                      if (next.has(selected)) next.delete(selected);
                      else next.add(selected);
                    }
                    return next;
                  })
                }
              >
                Collapse / expand
              </Button>
            </div>
            <ReactFlow
              onInit={setFlow}
              key={`${Object.keys(all).length}-${replaying}`}
              minZoom={0.01}
              nodes={graph}
              edges={visible
                .filter((n) => n.parent_id && nodes[n.parent_id])
                .map((n) => ({
                  id: n.node_id,
                  source: n.parent_id!,
                  target: n.node_id,
                  style: {
                    stroke: ancestors.has(n.node_id) ? "#69d5b1" : "#455265",
                  },
                }))}
              onNodeClick={(_, n) => setSelected(n.id)}
              fitView
              nodesDraggable={false}
            >
              <Background color="#293340" gap={24} />
              <Controls />
              <MiniMap />
            </ReactFlow>
            {replaying && !Object.keys(nodes).length && (
              <p className="overlay">No reconstructable nodes at this event.</p>
            )}
          </section>
          <section className="inspector">
            <h2>Candidate inspector</h2>
            {n ? (
              <>
                <code>{n.node_id}</code>
                <h3>{n.candidate?.strategy ?? "Root"}</h3>
                <p>{n.candidate?.explanation}</p>
                <p>
                  {n.status} · depth {n.depth} · visits {n.visits} · mean{" "}
                  {n.visits ? (n.total_reward / n.visits).toFixed(3) : "—"}
                </p>
                <Button
                  onClick={() =>
                    void navigator.clipboard.writeText(n.candidate?.code ?? "")
                  }
                >
                  Copy code
                </Button>
                <Button onClick={() => setDiff(!diff)}>Parent diff</Button>
                {diff ? (
                  <Suspense fallback={<p>Loading editor…</p>}>
                    <DiffEditor
                      height="350px"
                      language="python"
                      theme="vs-dark"
                      original={nodes[n.parent_id ?? ""]?.candidate?.code ?? ""}
                      modified={n.candidate?.code ?? ""}
                      options={{ readOnly: true }}
                    />
                  </Suspense>
                ) : (
                  <Suspense fallback={<pre>{n.candidate?.code}</pre>}>
                    <CodeEditor
                      height="350px"
                      language="python"
                      theme="vs-dark"
                      value={n.candidate?.code ?? ""}
                      options={{ readOnly: true, minimap: { enabled: false } }}
                    />
                  </Suspense>
                )}
                <Button
                  onClick={(e) =>
                    void e.currentTarget
                      .closest(".inspector")
                      ?.requestFullscreen()
                  }
                >
                  Full screen
                </Button>
                <h3>Visible evaluation</h3>
                <p>
                  {n.evaluation
                    ? `${n.evaluation.passed_tests} / ${n.evaluation.total_tests} passed · reward ${n.evaluation.reward ?? "unknown"}`
                    : "Not recorded at this point"}
                </p>
                {n.evaluation?.test_results.map((test, i) => (
                  <details key={i}>
                    <summary>
                      {String(test.test_id)} · {String(test.status)}
                    </summary>
                    <pre>{JSON.stringify(test, null, 2)}</pre>
                  </details>
                ))}
              </>
            ) : (
              <p className="muted">
                Select a node to inspect its candidate and evaluation.
              </p>
            )}
          </section>
        </div>
      )}
      {tab === "timeline" && (
        <section className="panel">
          <h2>Worker activity</h2>
          <select
            aria-label="Frontier filter"
            value={frontier}
            onChange={(e) => setFrontier(e.target.value)}
          >
            <option value="">All frontiers</option>
            {[
              ...new Set(
                timeline.data?.data.intervals
                  .map((i) => i.frontier_index)
                  .filter((i) => i != null),
              ),
            ].map((i) => (
              <option key={i!} value={String(i)}>
                Frontier {i}
              </option>
            ))}
          </select>
          <p className="muted">
            Peak observed concurrency:{" "}
            {timeline.data?.data.peak_concurrency ?? "Unknown"} · Open intervals
            have no recorded end.
          </p>
          <select
            aria-label="Worker filter"
            value={worker}
            onChange={(e) => setWorker(e.target.value)}
          >
            <option value="">All workers</option>
            {[
              ...new Set(timeline.data?.data.intervals.map((i) => i.worker_id)),
            ].map((w) => (
              <option key={w}>{w}</option>
            ))}
          </select>
          <label>
            Time zoom{" "}
            <input
              type="range"
              min="1"
              max="5"
              step="0.5"
              value={zoom}
              onChange={(e) => setZoom(+e.target.value)}
            />
          </label>
          <div className="activities">
            {timeline.data?.data.intervals
              .filter(
                (i) =>
                  (!worker || i.worker_id === worker) &&
                  (!frontier || String(i.frontier_index) === frontier),
              )
              .map((i, index) => {
                const list = timeline.data!.data.intervals;
                const start = Math.min(...list.map((x) => Date.parse(x.start)));
                const end = Math.max(
                  ...list.map((x) => Date.parse(x.end ?? x.start)),
                );
                const span = Math.max(1, end - start);
                return (
                  <div
                    className="activity"
                    style={{ minWidth: 600 * zoom }}
                    key={index}
                  >
                    <code>
                      {i.worker_id}
                      <small>{i.task_id}</small>
                    </code>
                    <div className="track">
                      <Button
                        className={
                          i.outcome?.includes("FAILED")
                            ? "failed"
                            : i.outcome?.includes("CANCELED")
                              ? "canceled"
                              : i.kind
                        }
                        title={`${i.start} → ${i.end ?? "Unknown"} · ${i.outcome ?? "incomplete"}`}
                        style={{
                          marginLeft: `${(100 * (Date.parse(i.start) - start)) / span}%`,
                          width: `${Math.max(1, (100 * (Date.parse(i.end ?? i.start) - Date.parse(i.start))) / span)}%`,
                        }}
                        onClick={() => {
                          if (i.candidate_id) {
                            setSelected(i.candidate_id);
                            setTab("tree");
                          }
                        }}
                      >
                        {i.kind}
                        {!i.end ? " ?" : ""}
                      </Button>
                    </div>
                  </div>
                );
              })}
          </div>
        </section>
      )}
      {tab === "analytics" && (
        <section className="panel">
          <h2>Search analytics</h2>
          <select
            aria-label="Chart time axis"
            value={axis}
            onChange={(e) => setAxis(e.target.value)}
          >
            <option value="sequence">Logical event sequence</option>
            <option value="elapsed">Elapsed seconds</option>
          </select>
          <div className="charts">
            <div>
              <h3>Candidate reward distribution</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={Array.from({ length: 11 }, (_, i) => ({
                    reward: i / 10,
                    count: Object.values(all).filter(
                      (n) =>
                        n.evaluation?.reward != null &&
                        Math.floor(n.evaluation.reward * 10) === i,
                    ).length,
                  }))}
                >
                  <XAxis dataKey="reward" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#69d5b1" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h3>Best visible reward by event</h3>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={chart}>
                  <XAxis dataKey={axis} />
                  <YAxis domain={[0, 1]} />
                  <Tooltip />
                  <Line dataKey="best" stroke="#69d5b1" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h3>Recorded token consumption</h3>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={chart}>
                  <XAxis dataKey={axis} />
                  <YAxis />
                  <Tooltip />
                  <Line dataKey="input" stroke="#79aaff" dot={false} />
                  <Line dataKey="output" stroke="#c1a3ff" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h3>Final lifecycle states</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={Object.entries(
                    (metrics.data?.data.statuses ?? {}) as Record<
                      string,
                      number
                    >,
                  ).map(([name, count]) => ({ name, count }))}
                >
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#79aaff" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <h3>Recorded frontier analysis</h3>
          <table>
            <thead>
              <tr>
                {[
                  "Frontier",
                  "Seconds",
                  "Generated",
                  "Evaluated",
                  "Retained",
                  "Pruned",
                  "Best reward",
                ].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(
                (metrics.data?.data.frontiers ?? []) as Record<
                  string,
                  number | null
                >[]
              ).map((f, i) => (
                <tr key={i}>
                  {[
                    "frontier",
                    "duration",
                    "generated",
                    "evaluated",
                    "retained",
                    "pruned",
                    "best_reward",
                  ].map((k) => (
                    <td key={k}>{f[k] ?? "Unknown"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <footer>
        <div className="playback" aria-label="Replay controls">
          <Button
            disabled={!detail.data?.data.detailed_replay}
            aria-label="Beginning"
            onClick={() => {
              setReplaying(true);
              setCursor(0);
            }}
          >
            <SkipBack size={16} />
          </Button>
          <Button
            disabled={!detail.data?.data.detailed_replay}
            aria-label="Previous event"
            onClick={() => {
              setReplaying(true);
              setPlaying(false);
              setCursor(Math.max(0, cursor - 1));
            }}
          >
            <ChevronLeft size={16} />
          </Button>
          <Button
            disabled={!detail.data?.data.detailed_replay}
            aria-label={playing ? "Pause" : "Play"}
            onClick={() => {
              setReplaying(true);
              setPlaying(!playing);
            }}
          >
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </Button>
          <Button
            disabled={!detail.data?.data.detailed_replay}
            aria-label="Next event"
            onClick={() => {
              setReplaying(true);
              setCursor(Math.min(trace.length, cursor + 1));
            }}
          >
            <ChevronRight size={16} />
          </Button>
          <Button
            disabled={!detail.data?.data.detailed_replay}
            aria-label="End"
            onClick={() => {
              setReplaying(true);
              setCursor(trace.length);
            }}
          >
            <SkipForward size={16} />
          </Button>
          <input
            disabled={!detail.data?.data.detailed_replay}
            aria-label="Replay position"
            type="range"
            min={0}
            max={trace.length}
            value={cursor}
            onChange={(e) => {
              setReplaying(true);
              setPlaying(false);
              setCursor(+e.target.value);
            }}
          />
          <select
            aria-label="Playback speed"
            value={speed}
            onChange={(e) => setSpeed(+e.target.value)}
          >
            {[0.5, 1, 2, 4].map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
          <code>
            {cursor} / {trace.length}
          </code>
        </div>
        <div className="metrics">
          {[
            "llm_calls",
            "total_tokens",
            "cost_usd",
            "elapsed_seconds",
            "candidates",
          ].map((k) => (
            <div key={k}>
              <small>{k.replaceAll("_", " ")}</small>
              <strong>
                {detail.data?.data.budget[k] == null
                  ? "Unknown"
                  : Number(detail.data.data.budget[k]).toLocaleString(
                      undefined,
                      { maximumFractionDigits: 3 },
                    )}
              </strong>
            </div>
          ))}
        </div>
      </footer>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
