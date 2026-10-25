"""Data contracts shared by the engine, the API, the agent and the frontend.

Agree on these on day one. CS2 builds screens against them using mocks while
CS1 builds the engine that fills them. Changing a field means telling the
other two people.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from neurosim import config


# --- Gene -> neurons (Bio) ----------------------------------------------------------


class Ortholog(BaseModel):
    human_gene: str                      # "PINK1"
    fly_genes: list[str]                 # ["Pink1"]; PARK7 -> ["dj-1beta", "DJ-1alpha"]
    diopt_score: int | None              # DIOPT support count; None if no ortholog
    relationship: str                    # "1:1", "1:2", "none"
    confidence: float                    # 0..1, from the DIOPT score


class PaperSource(BaseModel):
    """Where an approved paper-upload row came from (agent/papers.py)."""

    id: str                              # the proposal id, used to remove the row again
    by: str                              # Gemini model that proposed it
    file: str                            # uploaded file name, "pasted text" or the DOI
    quote: str                           # verbatim sentence behind the row
    page: int | None = None              # PDF page of the quote; None for text and DOIs
    quote_found: bool | None = None      # quote found word for word in the source; None if unchecked
    tier_reason: str = ""
    edited: list[str] = []               # fields Bio changed before approving
    approved_at: str


class EvidenceRow(BaseModel):
    """One published finding: in this fly model, these DA clusters were lost."""

    disease: str                         # "parkinsons"
    human_gene: str
    fly_gene: str
    model_type: str                      # "mutant", "RNAi", "overexpression"
    clusters: list[str]                  # ["PPL1"], ["PAM"], ["PPM3", "PPL2"]
    finding: str                         # one plain sentence a judge can read
    citation: str                        # "Whitworth et al. 2005, PNAS"
    url: str
    tier: str                            # "high" | "medium" | "low"
    verified_by_bio: bool = False        # flipped once Bio checks the paper figures
    extracted: PaperSource | None = None # set on rows approved from a paper upload


class CellTypeExpression(BaseModel):
    """A fly gene's expression in one FlyWire cell type, from Kait's atlas table.
    An annotation only: it never changes which neurons are seeds or their confidence."""

    cell_type: str                       # "PAM08"
    tpm: dict[str, float]                # fly gene -> TPM, mean over the atlas lines covering this type
    atlas_labels: list[str]              # ["dopaminergic PAM neuron 4"]
    match: str                           # "inferred" (one line per compartment) | "coarse" (a pooled line)


class GeneExpression(BaseModel):
    """What the expression atlas says about one gene's fly orthologs (bio/expression.py)."""

    human_gene: str
    fly_genes: list[str]                 # orthologs the atlas measured
    missing_fly_genes: list[str]         # orthologs it has no rows for (RabX4)
    clusters_measured: list[str]         # ["PAM"]: every other cluster is "not measured", which is neutral
    cell_types: list[CellTypeExpression]
    citation: str
    url: str


class TargetExpression(BaseModel):
    """A fly gene's atlas value in one downstream cell type (bio/targets.py). Context only."""

    tpm: dict[str, float]                # fly gene -> TPM
    atlas_label: str                     # "alpha/beta posterior Kenyon cell"
    match: str                           # "exact" | "coarse" (a pooled line) | "inferred" (a promoter fusion)
    fbbt_ids: list[str] = []             # FlyBase anatomy ids of the atlas label(s)
    note: str | None = None


class DirectTarget(BaseModel):
    """One FlyWire cell type that the gene's lost clusters synapse onto directly."""

    cell_type: str                       # "KCg-m"
    synapses: int                        # from the gene's clusters only
    by_cluster: dict[str, int]           # evidence cluster -> synapses, zeros left out
    n_neurons: int                       # neurons of this type that get any DA input (all five clusters)
    expression: TargetExpression | None = None   # None = not measured, never "not expressed"


class DirectTargets(BaseModel):
    """Where the lost dopamine neurons send their output, one synapse away.
    Connectivity from Kait's table, not a simulation result."""

    human_gene: str
    clusters: list[str]                  # evidence clusters the table covers
    clusters_not_covered: list[str]      # evidence clusters with no column (PPM3)
    total_synapses: int                  # onto every target type, not just the ones listed
    n_target_types: int
    targets: list[DirectTarget]          # top config.TOP_DIRECT_TARGETS by synapses
    n_types_with_expression: int         # target types the atlas measured, of n_target_types
    citation: str
    expression_citation: str | None = None
    expression_url: str | None = None


class SeedType(BaseModel):
    """A connectome cell type chosen as a starting point, and why."""

    cell_type: str                       # "PPL101"
    cluster: str                         # "PPL1"
    match: str                           # "exact" | "inferred"
    n_neurons: int
    root_ids: list[int]
    confidence: float                    # ortholog x tier x match (see bio/evidence.py)
    evidence: list[EvidenceRow]
    expression: CellTypeExpression | None = None   # PAM types only; None = not measured, never a veto


class SeedSet(BaseModel):
    disease: str
    human_gene: str
    ortholog: Ortholog
    seed_types: list[SeedType]
    expression: GeneExpression | None = None   # None when the atlas has none of the gene's orthologs

    @property
    def root_ids(self) -> list[int]:
        return [rid for t in self.seed_types for rid in t.root_ids]


# --- Simulation (CS1) ----------------------------------------------------------------


class PerturbationMode(str, Enum):
    KNOCKOUT = "knockout"                # seeds produce no output
    REDUCE_OUTPUT = "reduce_output"      # seeds' output scaled by (1 - strength)


class SimulationRequest(BaseModel):
    human_gene: str
    mode: PerturbationMode = PerturbationMode.KNOCKOUT
    strength: float = Field(1.0, ge=0.0, le=1.0)   # ignored for knockout
    hops: int = Field(config.HOPS, ge=1, le=5)
    decay: float = Field(config.DECAY, gt=0.0, le=1.0)
    high_confidence_only: bool = False   # drop low-tier evidence and inferred type matches
    seed_cell_types: list[str] | None = None   # restrict to these (agent follow-ups)


class GroupLevel(str, Enum):
    REGION = "region"                    # brain region / neuropil, e.g. "MB_ML_R"
    SUPER_REGION = "super_region"        # coarse: "mushroom body", "central complex"
    CELL_TYPE = "cell_type"              # e.g. "MBON05"
    SUPER_CLASS = "super_class"          # e.g. "central", "descending"


class GroupScore(BaseModel):
    group: str
    level: GroupLevel
    n_neurons: int
    mean_direct: float                   # mean share of input coming straight from seeds
    mean_impact: float                   # mean multi-hop impact score
    n_strong_hits: int                   # neurons with direct dependency >= STRONG_HIT
    null_mean: float                     # same score under random seeds
    null_sd: float
    z_score: float
    p_value: float                       # empirical, from the random draws
    q_value: float                       # FDR-corrected
    above_chance: bool                   # q_value < FDR_ALPHA and z > 0
    function_label: str | None = None    # plain words, from Bio: "learning and memory"


class NeuronImpact(BaseModel):
    root_id: int
    cell_type: str | None
    region: str | None
    direct: float
    impact: float
    per_hop: list[float]                 # impact contributed at hop 1, 2, 3


class SimulationResult(BaseModel):
    run_id: str                          # cache key, deterministic from the request
    request: SimulationRequest
    seeds: SeedSet
    n_seed_neurons: int
    n_reached: int                       # neurons with impact > 0 (excluding seeds)
    disruption_score: float              # 0..1, see engine/vulnerability.py
    disruption_null_mean: float
    disruption_z: float
    groups: dict[GroupLevel, list[GroupScore]]   # each list sorted by z_score desc
    top_neurons: list[NeuronImpact]      # top 50 by impact
    assumptions: dict[str, float | int | str]    # config values used, shown in the UI


# --- Drawing (CS1 -> CS2) -----------------------------------------------------------


class GraphNode(BaseModel):
    id: str
    label: str
    group: str                           # region, used for compound-node grouping
    is_seed: bool
    impact: float
    x: float | None = None               # fixed layout so before/after line up
    y: float | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float                        # input fraction
    synapses: int
    lost: float                          # how much of this edge's drive is removed


class Subgraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class SankeyLink(BaseModel):
    source: str                          # seed cluster, e.g. "PPL1"
    target: str                          # super region, e.g. "mushroom body"
    value: float                         # summed impact


class DegenerationFrame(BaseModel):
    t: float                             # simulated time in seconds
    region_activity: dict[str, float]    # region name → mean activity (0..1 normalised)
    seed_health: float                   # 1.0 at t=0, approaches 0.0


class DegenerationSeries(BaseModel):
    run_id: str
    frames: list[DegenerationFrame]
    dt: float                            # seconds per frame
    total_t: float
    n_regions: int
    model: str                           # "WCModel" (Wilson–Cowan; ALN is slower)


# --- Comparison (CS1) ---------------------------------------------------------------


class Comparison(BaseModel):
    run_a: str
    run_b: str
    level: GroupLevel
    spearman_rho: float                  # how similar the two group rankings are
    shared_top: list[str]                # in both top-N lists
    only_a: list[str]
    only_b: list[str]
    summary: str                         # one deterministic sentence, no LLM
