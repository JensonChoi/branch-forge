export type Candidate = {
  code: string;
  strategy: string | null;
  explanation: string;
};
export type Evaluation = {
  reward: number | null;
  passed_tests: number;
  total_tests: number;
  test_results: Record<string, unknown>[];
};
export type SearchNode = {
  node_id: string;
  parent_id: string | null;
  depth: number;
  status: string;
  candidate: Candidate | null;
  evaluation: Evaluation | null;
  visits: number;
  total_reward: number;
  worker_id?: string;
  provisional?: boolean;
};
export type Event = {
  sequence: number;
  event_type: string;
  timestamp: string;
  node_id?: string;
  candidate_id?: string;
  task_id?: string;
  worker_id?: string;
  parent_id?: string;
  node?: SearchNode;
  root?: SearchNode;
  candidate?: Candidate;
  evaluation?: Evaluation;
  reward?: number;
  input_tokens?: number;
  output_tokens?: number;
  duration_seconds?: number;
  frontier_index?: number;
};
export type State = {
  nodes: Record<string, SearchNode>;
  workers: Record<string, string>;
  selected: string | null;
  tokens: number;
  frontiers: number[];
};
export const initial = (): State => ({
  nodes: {},
  workers: {},
  selected: null,
  tokens: 0,
  frontiers: [],
});
export function applyEvent(previous: State, e: Event): State {
  const s: State = {
    ...previous,
    nodes: { ...previous.nodes },
    workers: { ...previous.workers },
    frontiers: [...previous.frontiers],
  };
  const id = e.node_id ?? e.candidate_id;
  if (e.event_type === "RUN_STARTED" && e.root) s.nodes.root = e.root;
  if (e.event_type === "CANDIDATE_GENERATED" && e.candidate && id)
    s.nodes[id] = {
      node_id: id,
      parent_id: e.parent_id ?? "root",
      depth: (s.nodes[e.parent_id ?? "root"]?.depth ?? 0) + 1,
      status: "PENDING",
      candidate: e.candidate,
      evaluation: null,
      visits: 0,
      total_reward: 0,
      provisional: true,
    };
  if (e.event_type === "NODE_CREATED" && e.node)
    s.nodes[e.node.node_id] = e.node;
  if (id && s.nodes[id]) {
    const n = { ...s.nodes[id] };
    if (e.event_type === "EVALUATION_STARTED") n.status = "EVALUATING";
    if (e.event_type === "CANDIDATE_EVALUATED" && e.evaluation) {
      n.evaluation = e.evaluation;
      n.status = e.evaluation.reward === null ? "FAILED" : "EVALUATED";
    }
    if (e.event_type === "NODE_PRUNED") n.status = "PRUNED";
    s.nodes[id] = n;
  }
  if (e.event_type === "REWARD_BACKPROPAGATED" && id) {
    let n = s.nodes[id];
    const seen = new Set<string>();
    while (n && !seen.has(n.node_id)) {
      seen.add(n.node_id);
      s.nodes[n.node_id] = {
        ...n,
        visits: n.visits + 1,
        total_reward: n.total_reward + (e.reward ?? 0),
      };
      n = s.nodes[n.parent_id ?? ""];
    }
  }
  if (e.event_type === "SUBAGENT_STARTED" && e.task_id)
    s.workers[e.task_id] = e.worker_id ?? e.task_id;
  if (
    ["SUBAGENT_FINISHED", "SUBAGENT_FAILED", "SUBAGENT_CANCELED"].includes(
      e.event_type,
    ) &&
    e.task_id
  )
    delete s.workers[e.task_id];
  if (e.event_type === "FINAL_SELECTED") s.selected = e.node_id ?? null;
  if (e.event_type === "LLM_FINISHED")
    s.tokens += (e.input_tokens ?? 0) + (e.output_tokens ?? 0);
  if (e.event_type === "FRONTIER_COMPLETED" && e.frontier_index !== undefined)
    s.frontiers.push(e.frontier_index);
  return s;
}
export class Replay {
  private checkpoints = new Map<number, State>([[0, initial()]]);
  constructor(
    public events: Event[],
    public interval = 100,
  ) {
    if (interval < 1) throw Error("Invalid checkpoint interval");
    let s = initial();
    events.forEach((e, i) => {
      s = applyEvent(s, e);
      if ((i + 1) % interval === 0) this.checkpoints.set(i + 1, s);
    });
  }
  seek(index: number): State {
    index = Math.max(0, Math.min(index, this.events.length));
    const base = Math.floor(index / this.interval) * this.interval;
    let s = this.checkpoints.get(base)!;
    for (let i = base; i < index; i++) s = applyEvent(s, this.events[i]);
    return s;
  }
}
