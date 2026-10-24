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

import json

from neurosim import config
from neurosim.models import EvidenceRow, Ortholog, SeedSet, SeedType, SimulationRequest

ALL_DA = "*"
TIER_ORDER = {"high": 3, "medium": 2, "low": 1}

# The Riemensperger 2013 validation case: alpha-synuclein in the ~15 PAM
# neurons per hemisphere that innervate the mushroom body beta-prime lobe.
# These are the PAM types whose compartments include beta-prime in the
# hemibrain/FlyWire naming (Li et al. 2020, eLife): b'2a, b2b'2a, b'2p, b'2m,
# b'1ap, b'1m, g5b'2a. Bio: check this list against the paper's driver line.
VALIDATION_PAM_TYPES = ["PAM02", "PAM03", "PAM05", "PAM06", "PAM13", "PAM14", "PAM15"]


class SeedError(ValueError):
    """A gene cannot be simulated as asked. The message is shown to the user."""


def load_evidence() -> dict:
    """Read data/evidence.json, plus the rows Bio approved from paper uploads
    in config.APPROVED_EVIDENCE_PATH if that file exists (same row shape, with
    an extra "extracted" block). Validate every evidence row against
    EvidenceRow and fail loudly on a row without a citation."""
    data = json.loads(config.EVIDENCE_PATH.read_text())
    raw_rows = [(config.EVIDENCE_PATH.name, raw) for raw in data.get("evidence", [])]
    if config.APPROVED_EVIDENCE_PATH.exists():
        approved = json.loads(config.APPROVED_EVIDENCE_PATH.read_text())
        raw_rows += [(config.APPROVED_EVIDENCE_PATH.name, raw) for raw in approved.get("evidence", [])]
    rows = []
    for i, (source, raw) in enumerate(raw_rows):
        row = EvidenceRow(**raw)
        if not row.citation.strip():
            raise ValueError(f"evidence row {i} in {source} ({row.human_gene}, {row.clusters}) has no citation")
        rows.append(row)
    data["evidence"] = rows
    return data


def _is_validation(row: EvidenceRow) -> bool:
    return row.finding.strip().upper().startswith("VALIDATION")


def list_diseases() -> list[str]:
    """Diseases present in the evidence table. Nothing disease-specific is
    hard-coded anywhere else, so adding a disease is a data change."""
    return sorted({row.disease for row in load_evidence()["evidence"]})


def list_genes(disease: str) -> list[dict]:
    """Genes for a disease with their ortholog and best evidence tier,
    for the gene picker. Include genes with no fly ortholog (SNCA) so the UI
    can show them as 'no fly ortholog' instead of hiding them, and ortholog
    entries listing this disease that have no evidence row yet, so the UI can
    say no paper names their clusters. why_not says which, None if simulatable."""
    table = load_evidence()
    rows = [row for row in table["evidence"] if row.disease == disease]
    listed = [gene for gene, entry in table["orthologs"].items()
              if isinstance(entry, dict) and disease in entry.get("diseases", [])]
    genes = []
    for gene in dict.fromkeys([row.human_gene for row in rows] + listed):
        try:
            ortholog = find_ortholog(gene)
        except SeedError:  # a gene only an uploaded paper mentions, not yet in the ortholog table
            ortholog = Ortholog(human_gene=gene, fly_genes=[], diopt_score=None,
                                relationship="not in the ortholog table", confidence=0.0)
        seeds = [row for row in rows if row.human_gene == gene and not _is_validation(row)]
        best = max((row.tier for row in seeds), key=TIER_ORDER.get, default=None)
        why_not = None
        if not ortholog.fly_genes:
            why_not = "no_ortholog"
        elif not seeds:
            why_not = "no_evidence"
        genes.append({
            "human_gene": gene,
            "fly_genes": ortholog.fly_genes,
            "relationship": ortholog.relationship,
            "ortholog_confidence": ortholog.confidence,
            "best_tier": best,
            "simulatable": why_not is None,
            "why_not": why_not,
        })
    return genes


def find_ortholog(human_gene: str) -> Ortholog:
    """Ortholog from the table. confidence: map the DIOPT score to 0..1
    (e.g. score / max possible score); 0 when there is no ortholog."""
    entry = load_evidence()["orthologs"].get(human_gene)
    if entry is None:
        raise SeedError(f"{human_gene} is not in the evidence table")
    fly_genes = list(entry.get("fly_genes", []))
    score = entry.get("diopt_score")
    if not fly_genes:
        confidence = 0.0
    elif score is None:
        confidence = config.UNSCORED_ORTHOLOG_CONFIDENCE
    else:
        confidence = min(score / config.DIOPT_MAX_SCORE, 1.0)
    return Ortholog(human_gene=human_gene, fly_genes=fly_genes, diopt_score=score,
                    relationship=entry.get("relationship", "none" if not fly_genes else "unknown"),
                    confidence=round(confidence, 3))


def evidence_for(human_gene: str, high_confidence_only: bool = False) -> list[EvidenceRow]:
    """Evidence rows for a gene. high_confidence_only drops tier 'low'.
    Never returns the SNCA validation row as a gene seed."""
    return [row for row in load_evidence()["evidence"]
            if row.human_gene == human_gene and not _is_validation(row)
            and not (high_confidence_only and row.tier == "low")]


def cluster_cell_types(cluster: str, high_confidence_only: bool = False) -> tuple[str, list[str]]:
    """(match, cell_types) for a cluster. high_confidence_only drops inferred matches."""
    entry = load_evidence().get("cluster_to_cell_types", {}).get(cluster)
    if entry is None:
        return "inferred", []
    match = entry.get("match", "inferred")
    if high_confidence_only and match != "exact":
        return match, []
    return match, list(entry.get("cell_types", []))


TYPE_COLUMNS = ("cell_type", "hemibrain_type")


def type_mask(neurons, cell_types: list[str]):
    """Neurons whose cell type is one of these names or a subtype of one
    ("PAM08" also matches "PAM08_a"). Checks cell_type and, when prep wrote
    it, hemibrain_type, because FlyWire splits some hemibrain types."""
    mask = None
    for column in TYPE_COLUMNS:
        if column not in neurons:
            continue
        values = neurons[column].astype("string")
        hit = values.isin(cell_types) | values.str.split("_").str[0].isin(cell_types)
        hit = hit.fillna(False)
        mask = hit if mask is None else mask | hit
    return mask.to_numpy(dtype=bool)


def _neurons():
    from neurosim.engine.graph import load_connectome

    return load_connectome().neurons


def _seed_types(rows: list[EvidenceRow], ortholog_confidence: float, high_confidence_only: bool,
                only_types: list[str] | None = None) -> list[SeedType]:
    neurons = _neurons()
    is_da = neurons["nt_type"].astype("string").str.lower().isin({"da", "dopamine"}).fillna(False)
    by_type: dict[str, SeedType] = {}
    for row in rows:
        tier = config.EVIDENCE_TIER_WEIGHT[row.tier]
        for cluster in row.clusters:
            match, cell_types = cluster_cell_types(cluster, high_confidence_only)
            for cell_type in cell_types:
                if only_types is not None and cell_type not in only_types:
                    continue
                if cell_type == ALL_DA:
                    members, name = neurons[is_da], "all DA neurons"
                else:
                    members, name = neurons[type_mask(neurons, [cell_type])], cell_type
                if members.empty:
                    continue
                confidence = round(ortholog_confidence * tier * config.TYPE_MATCH_WEIGHT[match], 3)
                seed = by_type.get(name)
                if seed is None:
                    by_type[name] = SeedType(cell_type=name, cluster=cluster, match=match, n_neurons=len(members),
                                             root_ids=[int(r) for r in members["root_id"]],
                                             confidence=confidence, evidence=[row])
                else:
                    seed.confidence = max(seed.confidence, confidence)
                    if row not in seed.evidence:
                        seed.evidence.append(row)
    return list(by_type.values())


def resolve_seeds(request: SimulationRequest) -> SeedSet:
    """The full chain for one request: ortholog, evidence, clusters, cell
    types, root IDs (from the connectome's neuron table) and confidences.

    If request.seed_cell_types is set, keep only those types (agent follow-ups
    like 'only PPL1'). Raise a clear error when the gene has no ortholog or no
    seeds survive the filters; the agent shows that error to the user.
    """
    gene = request.human_gene
    ortholog = find_ortholog(gene)
    if not ortholog.fly_genes:
        raise SeedError(f"{gene} has no fly ortholog, so it cannot be simulated in the fly connectome")
    rows = evidence_for(gene, request.high_confidence_only)
    if not rows:
        if request.high_confidence_only and evidence_for(gene):
            raise SeedError(f"no evidence rows for {gene} at medium or high tier")
        raise SeedError(f"{gene} has a fly ortholog ({', '.join(ortholog.fly_genes)}), but no paper in the evidence "
                        "table names the dopamine clusters lost in its fly models yet, so there are no seed neurons")
    seed_types = _seed_types(rows, ortholog.confidence, request.high_confidence_only)
    if request.seed_cell_types:
        wanted = set(request.seed_cell_types)
        seed_types = [t for t in seed_types if t.cell_type in wanted or t.cluster in wanted]
    if not seed_types:
        clusters = sorted({c for row in rows for c in row.clusters})
        raise SeedError(f"no connectome neurons found for {gene}: clusters {', '.join(clusters)} "
                        "have no matched cell types" + (" after the filters" if request.seed_cell_types
                                                       or request.high_confidence_only else ""))
    disease = rows[0].disease
    return SeedSet(disease=disease, human_gene=gene, ortholog=ortholog, seed_types=seed_types)


def validation_seeds() -> SeedSet:
    """The Riemensperger 2013 PAM seed set for the built-in validation check
    (docs/ENGINE_DESIGN.md, section 9)."""
    rows = [row for row in load_evidence()["evidence"] if _is_validation(row)]
    if not rows:
        raise SeedError("the evidence table has no validation row")
    row = rows[0]
    # A human transgene, not an ortholog, so the ortholog factor is 1.
    seed_types = _seed_types([row], 1.0, False, only_types=VALIDATION_PAM_TYPES)
    if not seed_types:
        raise SeedError(f"none of the validation PAM types {VALIDATION_PAM_TYPES} are in the connectome")
    ortholog = Ortholog(human_gene=row.human_gene, fly_genes=[], diopt_score=None, relationship="none (transgene)",
                        confidence=1.0)
    return SeedSet(disease=row.disease, human_gene=row.human_gene, ortholog=ortholog, seed_types=seed_types)
