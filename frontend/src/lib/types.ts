// Frontend names for the API contracts. Everything here comes from
// api-types.ts, which is generated from FastAPI's OpenAPI schema
// (npm run gen:api), so the shapes follow backend/neurosim/models.py.

import type { components } from "./api-types";

type S = components["schemas"];

export type SeedSet = S["SeedSet"];
export type SeedType = S["SeedType"];
export type EvidenceRow = S["EvidenceRow"];
export type Ortholog = S["Ortholog"];
export type SimulationRequest = S["SimulationRequest"];
export type SimulationResult = S["SimulationResult"];
export type GroupScore = S["GroupScore"];
export type GroupLevel = S["GroupLevel"];
export type PerturbationMode = S["PerturbationMode"];
export type SankeyLink = S["SankeyLink"];
export type Subgraph = S["Subgraph"];
export type GraphNode = S["GraphNode"];
export type GraphEdge = S["GraphEdge"];
export type Comparison = S["Comparison"];

// The endpoints below return untyped dicts in main.py; these mirror their
// docstrings.

/** GET /diseases/{d}/genes */
export interface GeneOption {
  human_gene: string;
  fly_genes: string[];
  best_tier: "high" | "medium" | "low" | null;
  simulatable: boolean;
}

/** GET /runs/{id}/neurons/{rid}/explain */
export interface NeuronExplanation {
  root_id: number;
  paths: { neurons: string[]; strength: number }[];
}

/** POST /agent/chat */
export interface ChatRequest {
  message: string;
  /** The last reply's interaction_id; Gemini keeps the history behind it. */
  interaction_id: string | null;
  /** What the results view shows, so "what if they lose half?" has a subject. */
  context: { active_run: Record<string, unknown> } | null;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  /** Set when the tool failed; the agent was told and explains it. */
  error?: string | null;
}

export interface AgentReply {
  reply: string;
  tool_calls: ToolCall[];
  run_ids: string[];
  interaction_id: string | null;
  model?: string;
}

/** POST /runs/{id}/summary. Every number is copied from the run, not written by Gemini. */
export interface RunSummary {
  run_id: string;
  headline: string;
  top_circuits: {
    group: string;
    level: GroupLevel;
    why: string;
    z_score: number;
    above_chance: boolean;
    function_label: string | null;
  }[];
  caveats: string[];
  next_experiment: {
    description: string;
    why: string;
    request: Pick<SimulationRequest, "human_gene" | "mode" | "strength" | "seed_cell_types"> | null;
  };
  model: string;
}

/** POST /evidence/extract: rows Gemini proposes from a paper, each waiting for Bio. */
export interface EvidenceProposal {
  id: string;
  status: "pending" | "approved" | "rejected";
  disease: string;
  human_gene: string;
  fly_gene: string;
  model_type: string;
  clusters: string[];
  finding: string;
  tier: "high" | "medium" | "low";
  tier_reason: string;
  quote: string;
  page: number;
  citation: string;
  url: string;
}

export interface EvidenceExtraction {
  citation: string;
  url: string;
  file: string;
  model: string;
  rows: EvidenceProposal[];
}
