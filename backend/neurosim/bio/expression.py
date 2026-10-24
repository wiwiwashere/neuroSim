"""Expression of a gene's fly orthologs in connectome cell types (Bio + CS2).

Kait's table (data/expression_table.csv) is bulk RNA-seq of genetically
labelled cell types from Davis et al. 2020. evidence.json's "expression"
block maps its labels to FlyWire cell types; only PAM is covered.

This is an annotation on the mapping chain and nothing more. It never
removes a seed and never changes a seed's confidence: most PD genes are
expressed broadly, bulk RNA-seq misses low transcripts, and a cluster the
atlas didn't profile (PPL1, PPL2, PPM1/2, PPM3, PAL) is "not measured",
not "not expressed". Whether expression should weigh into confidence is
for Bio and CS1 to decide (see the kait-celltype-map README).
"""

from __future__ import annotations

import pandas as pd

from neurosim import config
from neurosim.models import CellTypeExpression, GeneExpression, SeedSet


def _block(table: dict) -> dict | None:
    block = table.get("expression")
    if not block or not config.EXPRESSION_PATH.exists():
        return None
    return block


def _rows(block: dict) -> pd.DataFrame:
    """The atlas rows for the head samples, with fly genes under their fly_genes symbols."""
    rows = pd.read_csv(config.EXPRESSION_PATH)
    rows = rows[rows["experiment"] == block["experiment"]].dropna(subset=["expression"])
    names = block.get("fly_gene_names", {})
    return rows.assign(fly_gene=rows["gene"].map(lambda g: names.get(g, g)))


def gene_expression(human_gene: str, table: dict | None = None) -> GeneExpression | None:
    """The atlas values for every cell type it covers, for this gene's fly
    orthologs. None when the table or the gene's orthologs aren't in it."""
    from neurosim.bio import evidence

    table = table or evidence.load_evidence()
    block = _block(table)
    entry = table["orthologs"].get(human_gene)
    if block is None or not isinstance(entry, dict) or not entry.get("fly_genes"):
        return None
    fly_genes = list(entry["fly_genes"])
    rows = _rows(block)
    rows = rows[rows["fly_gene"].isin(fly_genes)]
    measured = [f for f in fly_genes if f in set(rows["fly_gene"])]
    if not measured:
        return None

    # FlyWire type -> the atlas labels that cover it, split by how precise the line is.
    covering: dict[str, dict[str, list[str]]] = {}
    for label, mapping in block["cell_types"].items():
        for cell_type in mapping["cell_types"]:
            covering.setdefault(cell_type, {}).setdefault(mapping["match"], []).append(label)

    cell_types = []
    for cell_type in sorted(covering):
        # A line labelling one compartment says more about a type than a line pooling five.
        match = "inferred" if "inferred" in covering[cell_type] else "coarse"
        labels = covering[cell_type][match]
        hits = rows[rows["cell_type"].isin(labels)]
        tpm = {f: round(float(v), 1) for f, v in hits.groupby("fly_gene")["expression"].mean().items()}
        if tpm:
            cell_types.append(CellTypeExpression(cell_type=cell_type, tpm=tpm, atlas_labels=labels, match=match))

    clusters = sorted({mapping["cluster"] for mapping in block["cell_types"].values()})
    return GeneExpression(
        human_gene=human_gene, fly_genes=measured, missing_fly_genes=[f for f in fly_genes if f not in measured],
        clusters_measured=clusters, cell_types=cell_types, citation=block["citation"], url=block["url"],
    )


def annotate(seeds: SeedSet) -> SeedSet:
    """Attach the atlas values to the seed set and to each seed type it covers.
    Seeds and confidences are left exactly as they were."""
    seeds.expression = gene_expression(seeds.human_gene)
    if seeds.expression is not None:
        by_type = {e.cell_type: e for e in seeds.expression.cell_types}
        for seed_type in seeds.seed_types:
            seed_type.expression = by_type.get(seed_type.cell_type)
    return seeds
