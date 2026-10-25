// Frontend names for the API contracts. Everything here comes from
// api-types.ts, which is generated from FastAPI's OpenAPI schema
// (npm run gen:api), so the shapes follow backend/neurosim/models.py.

import type { components } from "./api-types";

type S = components["schemas"];

export type SeedSet = S["SeedSet"];
export type SeedType = S["SeedType"];
export type EvidenceRow = S["EvidenceRow"];
export type PaperSource = S["PaperSource"];
export type UserSource = S["UserSource"];
export type Ortholog = S["Ortholog"];
export type GeneExpression = S["GeneExpression"];
export type CellTypeExpression = S["CellTypeExpression"];
export type DirectTargets = S["DirectTargets"];
export type DirectTarget = S["DirectTarget"];
export type TargetExpression = S["TargetExpression"];
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
  /** Why it can't be simulated: no fly ortholog, or an ortholog but no paper naming the lost clusters yet. */
  why_not: "no_ortholog" | "no_evidence" | null;
}

/** GET /runs/{id}/neurons/{rid}/explain */
export interface NeuronExplanation {
  root_id: number;
  paths: { neurons: string[]; strength: number }[];
}

/** GET /runs/{id}/dynamics — one Wilson–Cowan / neurolib snapshot. */
export interface DegenerationFrame {
  t: number;
  region_activity: Record<string, number>;
  seed_health: number;
}

export interface DegenerationSeries {
  run_id: string;
  frames: DegenerationFrame[];
  dt: number;
  total_t: number;
  n_regions: number;
  model: string;
}

/** GET /agent/llm: the model family behind the agent (NEUROSIM_LLM). */
export interface LlmInfo {
  family: "gemma" | "gemini";
  name: string;
  model: string;
  fallback_model: string;
}

/** POST /agent/chat */
export interface ChatRequest {
  message: string;
  /** The last reply's interaction_id; the backend (or Gemini's server) keeps the history behind it. */
  interaction_id: string | null;
  /** What the results view shows, so "what if they lose half?" has a subject. */
  context: {
    active_run: Record<string, unknown>;
    /** Open tab, Network view and picked neuron, so "the 3D thing" has a referent too. */
    view?: {
      tab: string;
      network_view: string;
      selected_neuron: { label: string; region: string; is_seed: boolean; impact: number } | null;
    };
  } | null;
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

/** POST /runs/{id}/summary. Every number is copied from the run, not written by the model. */
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

/** What a proposed row would do in a simulation (agent/papers.py check_row). */
export interface RowChecks {
  ortholog: { known: boolean; fly_genes: string[]; fly_gene_matches: boolean; confidence: number };
  /** in_quote: the supporting quote names this cluster. */
  clusters: { name: string; known: boolean; match: "exact" | "inferred" | null; n_cell_types: number; in_quote: boolean }[];
  /** ortholog x tier x best cluster match, as the seeds would get; null when it can't seed. */
  confidence: number | null;
  can_seed: boolean;
  duplicate: boolean;
  /** Plain sentences, empty when the row is ready to approve. */
  problems: string[];
}

export type EvidenceTier = "high" | "medium" | "low";

/** POST /evidence/extract: rows the model proposes from a paper, each waiting for Bio. */
export interface EvidenceProposal {
  id: string;
  status: "pending" | "approved" | "rejected" | "removed";
  disease: string;
  human_gene: string;
  fly_gene: string;
  model_type: string;
  clusters: string[];
  finding: string;
  tier: EvidenceTier;
  tier_reason: string;
  quote: string;
  /** PDF page the quote was found on; null for pasted text and DOIs. */
  page: number | null;
  /** Quote found word for word in the paper's text; null when too short to check. */
  quote_found: boolean | null;
  citation: string;
  url: string;
  source_file: string;
  /** What the model read: "PDF", "pasted text", "full text" or "abstract". */
  read: string;
  extracted_by: string;
  edited: string[];
  checks: RowChecks;
}

/** Fields Bio may correct before approving. */
export type EvidenceEdits = Partial<Pick<EvidenceProposal, "human_gene" | "fly_gene" | "model_type" | "clusters" | "finding" | "tier">>;

/** One of these goes to POST /evidence/extract. */
export type PaperInput = { file: File } | { text: string } | { doi: string };

export interface EvidenceExtraction {
  citation: string;
  url: string;
  file: string;
  read: string;
  /** Set when the result is weaker than it looks, e.g. only the abstract was available. */
  note: string | null;
  model: string;
  /** The main model was busy and the backup one read the paper. */
  fallback: boolean;
  rows: EvidenceProposal[];
}

// --- User-supplied diseases (bio/custom.py) ---------------------------------------

/** One row as the person wrote it (CSV/JSON column names or the form). */
export interface CustomRowInput {
  disease?: string;
  human_gene: string;
  fly_gene?: string;
  /** Dopamine clusters and/or FlyWire cell types; a string is split on ; */
  affected: string[] | string;
  model_type?: string;
  finding?: string;
  citation?: string;
  url?: string;
  tier?: EvidenceTier | "";
}

/** What one affected name resolved to. */
export interface AffectedCheck {
  name: string;
  kind: "cluster" | "cell_type" | "unknown" | "unchecked";
  match: "exact" | "inferred" | null;
  n_cell_types: number;
  n_neurons: number | null;
  dopamine: boolean | null;
  suggestions: string[];
}

export interface CustomRowChecks {
  ortholog: { known: boolean; fly_genes: string[]; confidence: number; user_supplied: boolean };
  affected: AffectedCheck[];
  confidence: number | null;
  can_seed: boolean;
  /** Stops the save. */
  problems: string[];
  /** Worth knowing, doesn't stop the save (non-dopamine seeds, your own ortholog call). */
  notes: string[];
}

/** A row after POST /custom/preview: normalised, with its checks. */
export interface CustomRow {
  disease: string;
  human_gene: string;
  fly_gene: string;
  affected: string[];
  model_type: string;
  finding: string;
  citation: string;
  url: string;
  tier: EvidenceTier;
  checks: CustomRowChecks;
}

export interface CustomPreview {
  disease: { id: string; name: string };
  file: string;
  rows: CustomRow[];
  ok: boolean;
  /** Problems with the upload as a whole (no name, two diseases, a built-in name). */
  problems: string[];
}

/** GET /custom/diseases: a saved user-supplied disease. */
export interface CustomDisease {
  id: string;
  name: string;
  file: string;
  added_at: string;
  n_rows: number;
  genes: string[];
  rows: {
    human_gene: string;
    fly_gene: string;
    affected: string[];
    tier: EvidenceTier;
    finding: string;
    citation: string;
    url: string;
    model_type: string;
    non_dopamine: string[];
  }[];
}

/** GET /custom/names: autocomplete for affected names. */
export interface NameMatch {
  name: string;
  kind: "cluster" | "cell_type";
  n_neurons: number | null;
  dopamine: boolean;
}

export type CustomInput = { file: File; disease?: string } | { rows: CustomRowInput[]; disease?: string };
