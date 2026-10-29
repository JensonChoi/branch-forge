import { describe, it, expect } from "vitest";
import {
  Replay,
  applyEvent,
  initial,
  type Event,
  type SearchNode,
} from "../src/replay";
const root: SearchNode = {
  node_id: "root",
  parent_id: null,
  depth: 0,
  status: "PENDING",
  candidate: null,
  evaluation: null,
  visits: 0,
  total_reward: 0,
};
const events: Event[] = [
  { sequence: 1, event_type: "RUN_STARTED", timestamp: "", root },
  {
    sequence: 2,
    event_type: "CANDIDATE_GENERATED",
    timestamp: "",
    candidate_id: "a",
    parent_id: "root",
    candidate: { code: "print(1)", strategy: "test", explanation: "test" },
  },
  {
    sequence: 3,
    event_type: "EVALUATION_STARTED",
    timestamp: "",
    candidate_id: "a",
  },
  { sequence: 4, event_type: "NODE_PRUNED", timestamp: "", node_id: "a" },
  { sequence: 5, event_type: "FINAL_SELECTED", timestamp: "", node_id: "a" },
];
describe("replay", () => {
  it("does not reveal future candidates or status", () => {
    const r = new Replay(events, 2);
    expect(r.seek(1).nodes.a).toBeUndefined();
    expect(r.seek(2).nodes.a.status).toBe("PENDING");
    expect(r.seek(3).nodes.a.status).toBe("EVALUATING");
    expect(r.seek(4).nodes.a.status).toBe("PRUNED");
    expect(r.seek(4).selected).toBeNull();
    expect(r.seek(5).selected).toBe("a");
  });
  it("matches reduction after arbitrary seeking and preserves checkpoints", () => {
    const r = new Replay(events, 2);
    const final = events.reduce(applyEvent, initial());
    expect(r.seek(5)).toEqual(final);
    r.seek(1);
    expect(r.seek(5)).toEqual(final);
    expect(r.seek(2).nodes.a.status).toBe("PENDING");
  });
  it("handles unknown events without inventing nodes", () => {
    expect(
      applyEvent(initial(), {
        sequence: 1,
        event_type: "UNKNOWN",
        timestamp: "",
      }),
    ).toEqual(initial());
  });
  it("bounds seek work for 5000 events", () => {
    const trace = Array.from({ length: 5000 }, (_, i) => ({
      sequence: i + 1,
      event_type: "LLM_FINISHED",
      timestamp: "",
      input_tokens: 1,
    }));
    const r = new Replay(trace);
    expect(r.seek(4999).tokens).toBe(4999);
  });
});

it("replays worker reuse, frontier completion and MCTS updates", () => {
  let state = events.slice(0, 2).reduce(applyEvent, initial());
  state = applyEvent(state, {
    sequence: 3,
    event_type: "SUBAGENT_STARTED",
    timestamp: "",
    task_id: "t1",
    worker_id: "w1",
  });
  expect(state.workers.t1).toBe("w1");
  state = applyEvent(state, {
    sequence: 4,
    event_type: "SUBAGENT_CANCELED",
    timestamp: "",
    task_id: "t1",
  });
  expect(state.workers).toEqual({});
  state = applyEvent(state, {
    sequence: 5,
    event_type: "REWARD_BACKPROPAGATED",
    timestamp: "",
    node_id: "a",
    reward: 0.5,
  });
  expect(state.nodes.root.visits).toBe(1);
  expect(state.nodes.a.total_reward).toBe(0.5);
  state = applyEvent(state, {
    sequence: 6,
    event_type: "FRONTIER_COMPLETED",
    timestamp: "",
    frontier_index: 0,
  });
  expect(state.frontiers).toEqual([0]);
});
