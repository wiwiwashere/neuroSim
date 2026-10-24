// Every request the app makes goes through here.
//
// Live mode: requests go to /api/*, which next.config.ts proxies to the
// FastAPI server (NEUROSIM_API_URL, default http://127.0.0.1:8000).
//
// Snapshot mode (NEXT_PUBLIC_DEMO_SNAPSHOT=1): the same calls read JSON files
// from public/demo/, written by scripts/snapshot.mjs, so the demo works with
// the backend down. snapshotPath() is the one mapping both sides share.

import type {
  AgentReply,
  ChatMessage,
  Comparison,
  GeneOption,
  GroupLevel,
  NeuronExplanation,
  SankeyLink,
  SeedSet,
  SimulationRequest,
  SimulationResult,
  Subgraph,
} from "./types";
import { snapshotPath } from "./snapshot-keys";

export const SNAPSHOT_MODE = process.env.NEXT_PUBLIC_DEMO_SNAPSHOT === "1";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = SNAPSHOT_MODE ? `/demo/${snapshotPath(path, init?.body as string | undefined)}` : `/api${path}`;
  const res = await fetch(url, SNAPSHOT_MODE ? undefined : { ...init, headers: { "Content-Type": "application/json" } });
  if (!res.ok) {
    const detail = SNAPSHOT_MODE ? "not in the demo snapshot" : await res.text().catch(() => "");
    throw new ApiError(`${init?.method ?? "GET"} ${path} failed (${res.status}) ${detail}`.trim(), res.status);
  }
  return res.json() as Promise<T>;
}

const q = (params: Record<string, string | boolean | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : "";
};

export const api = {
  diseases: () => request<string[]>("/diseases"),
  genes: (disease: string) => request<GeneOption[]>(`/diseases/${encodeURIComponent(disease)}/genes`),
  chain: (gene: string, highConfidenceOnly: boolean) =>
    request<SeedSet>(
      `/genes/${encodeURIComponent(gene)}/chain${q({ high_confidence_only: highConfidenceOnly || undefined })}`,
    ),
  simulate: (body: SimulationRequest) =>
    request<SimulationResult>("/simulate", { method: "POST", body: JSON.stringify(body) }),
  run: (runId: string) => request<SimulationResult>(`/runs/${encodeURIComponent(runId)}`),
  sankey: (runId: string) => request<SankeyLink[]>(`/runs/${encodeURIComponent(runId)}/sankey`),
  subgraph: (runId: string) => request<Subgraph>(`/runs/${encodeURIComponent(runId)}/subgraph`),
  explain: (runId: string, rootId: number) =>
    request<NeuronExplanation>(`/runs/${encodeURIComponent(runId)}/neurons/${rootId}/explain`),
  compare: (runA: string, runB: string, level: GroupLevel) =>
    request<Comparison>(`/compare${q({ run_a: runA, run_b: runB, level })}`),
  agentChat: (messages: ChatMessage[]) =>
    request<AgentReply>("/agent/chat", { method: "POST", body: JSON.stringify({ messages }) }),
};

/** FlyWire Codex page for one neuron: the real 3D shape, no renderer of our own. */
export const codexUrl = (rootId: number | string) =>
  `https://codex.flywire.ai/app/cell_details?root_id=${rootId}&data_version=783`;
