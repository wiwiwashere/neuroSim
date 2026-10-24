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
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
}

export interface AgentReply {
  reply: string;
  tool_calls: ToolCall[];
  run_ids: string[];
}
