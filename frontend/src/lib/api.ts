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
  ChatRequest,
  Comparison,
  CustomDisease,
  CustomInput,
  CustomPreview,
  CustomRowInput,
  DegenerationSeries,
  DirectTargets,
  EvidenceEdits,
  EvidenceExtraction,
  EvidenceProposal,
  EvidenceRow,
  GeneExpression,
  GeneOption,
  GroupLevel,
  LlmInfo,
  NameMatch,
  NeuronExplanation,
  PaperInput,
  RunSummary,
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

// FastAPI always answers errors in JSON, so a 5xx with a non-JSON body (or a
// fetch that throws) means the Next proxy gave up on it. A quick failure is a
// refused connection, usually uvicorn restarting under --reload: retry after
// these waits, then say so plainly. A slow one is the proxy's 5-minute timeout
// (next.config.ts): the API is busy, so sending the request again would only
// stack another one behind it.
const RETRY_DELAYS_MS = [1000, 2000];
const QUICK_FAILURE_MS = 10_000;
const UNREACHABLE = "Can't reach the neuroSim API on :8000. It may be restarting or stopped. Try again in a moment.";
const TIMED_OUT =
  "The neuroSim API didn't answer within 5 minutes, so the request was dropped. The API log shows what it was waiting on.";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = SNAPSHOT_MODE ? `/demo/${snapshotPath(path, init?.body as string | undefined)}` : `/api${path}`;
  if (SNAPSHOT_MODE) {
    const res = await fetch(url);
    if (!res.ok) throw new ApiError(`${init?.method ?? "GET"} ${path} failed (${res.status}) not in the demo snapshot`, res.status);
    return res.json() as Promise<T>;
  }
  const json = typeof init?.body === "string";
  for (let attempt = 0; ; attempt++) {
    const started = Date.now();
    const res = await fetch(url, { ...init, headers: json ? { "Content-Type": "application/json" } : undefined }).catch(() => null);
    if (res?.ok) return res.json() as Promise<T>;
    const text = res ? await res.text().catch(() => "") : "";
    let body: { detail?: unknown } | undefined;
    try {
      body = JSON.parse(text) as { detail?: unknown };
    } catch {}
    if (!res || (res.status >= 500 && body === undefined)) {
      if (Date.now() - started > QUICK_FAILURE_MS) throw new ApiError(TIMED_OUT, res?.status ?? 0);
      if (attempt < RETRY_DELAYS_MS.length) {
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
        continue;
      }
      throw new ApiError(UNREACHABLE, res?.status ?? 0);
    }
    // FastAPI's errors carry a plain-words message in "detail": show that alone.
    const detail = body?.detail;
    if (typeof detail === "string" && detail) throw new ApiError(detail, res.status);
    throw new ApiError(`${init?.method ?? "GET"} ${path} failed (${res.status}) ${text}`.trim(), res.status);
  }
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
  chain: (gene: string, highConfidenceOnly: boolean, disease?: string) =>
    request<SeedSet>(
      `/genes/${encodeURIComponent(gene)}/chain${q({ high_confidence_only: highConfidenceOnly || undefined, disease })}`,
    ),
  expression: (gene: string) => request<GeneExpression | null>(`/genes/${encodeURIComponent(gene)}/expression`),
  targets: (gene: string, highConfidenceOnly: boolean, disease?: string) =>
    request<DirectTargets | null>(
      `/genes/${encodeURIComponent(gene)}/targets${q({ high_confidence_only: highConfidenceOnly || undefined, disease })}`,
    ),
  simulate: (body: SimulationRequest) =>
    request<SimulationResult>("/simulate", { method: "POST", body: JSON.stringify(body) }),
  run: (runId: string) => request<SimulationResult>(`/runs/${encodeURIComponent(runId)}`),
  sankey: (runId: string) => request<SankeyLink[]>(`/runs/${encodeURIComponent(runId)}/sankey`),
  subgraph: (runId: string) => request<Subgraph>(`/runs/${encodeURIComponent(runId)}/subgraph`),
  dynamics: (runId: string, nRegions = 10, T = 10) =>
    request<DegenerationSeries>(
      `/runs/${encodeURIComponent(runId)}/dynamics${q({ n_regions: String(nRegions), T: String(T) })}`,
    ),
  explain: (runId: string, rootId: number) =>
    request<NeuronExplanation>(`/runs/${encodeURIComponent(runId)}/neurons/${rootId}/explain`),
  compare: (runA: string, runB: string, level: GroupLevel) =>
    request<Comparison>(`/compare${q({ run_a: runA, run_b: runB, level })}`),
  llm: () => request<LlmInfo>("/agent/llm"),
  agentChat: (body: ChatRequest) => request<AgentReply>("/agent/chat", { method: "POST", body: JSON.stringify(body) }),
  runSummary: (runId: string) => request<RunSummary>(`/runs/${encodeURIComponent(runId)}/summary`, { method: "POST" }),
  extractEvidence: (input: PaperInput) => {
    const form = new FormData();
    if ("file" in input) form.append("file", input.file);
    else if ("text" in input) form.append("text", input.text);
    else form.append("doi", input.doi);
    return request<EvidenceExtraction>("/evidence/extract", { method: "POST", body: form });
  },
  pendingEvidence: () => request<EvidenceProposal[]>("/evidence/proposals"),
  decideEvidence: (rowId: string, approve: boolean, edits?: EvidenceEdits) =>
    request<EvidenceProposal>(`/evidence/rows/${encodeURIComponent(rowId)}/decision`, {
      method: "POST",
      body: JSON.stringify({ approve, edits: edits && Object.keys(edits).length ? edits : null }),
    }),
  approvedEvidence: () => request<EvidenceRow[]>("/evidence/approved"),
  removeEvidence: (rowId: string) =>
    request<{ removed: string }>(`/evidence/approved/${encodeURIComponent(rowId)}`, { method: "DELETE" }),
  // User-supplied diseases (bio/custom.py).
  customDiseases: () => request<CustomDisease[]>("/custom/diseases"),
  previewCustom: (input: CustomInput) => {
    const form = new FormData();
    if ("file" in input) form.append("file", input.file);
    else form.append("rows", JSON.stringify(input.rows));
    if (input.disease) form.append("disease", input.disease);
    return request<CustomPreview>("/custom/preview", { method: "POST", body: form });
  },
  saveCustom: (body: { name: string; file: string; rows: CustomRowInput[] }) =>
    request<CustomDisease>("/custom/diseases", { method: "POST", body: JSON.stringify(body) }),
  removeCustom: (id: string) => request<{ removed: string }>(`/custom/diseases/${encodeURIComponent(id)}`, { method: "DELETE" }),
  customNames: (query: string) => request<NameMatch[]>(`/custom/names${q({ q: query })}`),
};

/** Downloadable templates for a user-supplied disease table (served by the API). */
export const customTemplateUrl = (format: "csv" | "json") => `/api/custom/template.${format}`;

/** FlyBase page for an anatomy ontology term (FBbt_00110931 -> FBbt:00110931). */
export const flybaseTermUrl = (fbbt: string) => `https://flybase.org/reports/${fbbt.replace("_", ":")}`;

/** FlyWire Codex page for one neuron: the real 3D shape, no renderer of our own. */
export const codexUrl = (rootId: number | string) =>
  `https://codex.flywire.ai/app/cell_details?root_id=${rootId}&data_version=783`;
