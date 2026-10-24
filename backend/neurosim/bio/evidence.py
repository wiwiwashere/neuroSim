"""Gene -> fly gene -> dying DA clusters -> connectome seed neurons (Bio + CS1).

Bio owns the content (data/evidence.json). CS1 owns the code below.

The chain, each link with its own confidence:

    human gene --(DIOPT)--> fly gene            ortholog confidence
    fly gene --(papers)--> DA clusters lost      evidence tier
    cluster --(Codex names)--> cell types        exact or inferred match
    cell type --(connectome)--> root IDs         (no uncertainty)

    seed type confidence = ortholog x tier weight x match weight
    (weights in config.EVIDENCE_TIER_WEIGHT and config.TYPE_MATCH_WEIGHT)

Why seeds come from phenotype papers, not gene expression: Pink1 and park are
expressed in nearly every cell, so expression would select most of the brain.
What is specific is which neurons DIE in fly models, so that is the bridge.
"""

from __future__ import annotations

from neurosim.models import EvidenceRow, Ortholog, SeedSet, SimulationRequest


def load_evidence() -> dict:
    """Read data/evidence.json, plus the rows Bio approved from paper uploads
    in config.APPROVED_EVIDENCE_PATH if that file exists (same row shape, with
    an extra "extracted" block). Validate every evidence row against
    EvidenceRow and fail loudly on a row without a citation."""
    raise NotImplementedError


def list_diseases() -> list[str]:
    """Diseases present in the evidence table. Nothing disease-specific is
    hard-coded anywhere else, so adding a disease is a data change."""
    raise NotImplementedError


def list_genes(disease: str) -> list[dict]:
    """Genes for a disease with their ortholog and best evidence tier,
    for the gene picker. Include genes with no fly ortholog (SNCA) so the UI
    can show them as 'no fly ortholog' instead of hiding them."""
    raise NotImplementedError


def find_ortholog(human_gene: str) -> Ortholog:
    """Ortholog from the table. confidence: map the DIOPT score to 0..1
    (e.g. score / max possible score); 0 when there is no ortholog."""
    raise NotImplementedError


def evidence_for(human_gene: str, high_confidence_only: bool = False) -> list[EvidenceRow]:
    """Evidence rows for a gene. high_confidence_only drops tier 'low'.
    Never returns the SNCA validation row as a gene seed."""
    raise NotImplementedError


def cluster_cell_types(cluster: str, high_confidence_only: bool = False) -> tuple[str, list[str]]:
    """(match, cell_types) for a cluster. high_confidence_only drops inferred matches."""
    raise NotImplementedError


def resolve_seeds(request: SimulationRequest) -> SeedSet:
    """The full chain for one request: ortholog, evidence, clusters, cell
    types, root IDs (from the connectome's neuron table) and confidences.

    If request.seed_cell_types is set, keep only those types (agent follow-ups
    like 'only PPL1'). Raise a clear error when the gene has no ortholog or no
    seeds survive the filters; the agent shows that error to the user.
    """
    raise NotImplementedError


def validation_seeds() -> SeedSet:
    """The Riemensperger 2013 PAM seed set for the built-in validation check
    (docs/ENGINE_DESIGN.md, section 9)."""
    raise NotImplementedError
