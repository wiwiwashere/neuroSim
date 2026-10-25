"""Where a gene's lost dopamine neurons send their output, one synapse away (Bio + CS2).

Kait's table (data/downstream_by_flywire_type.csv) lists every FlyWire cell
type that receives synapses from the PAL, PAM, PPL1, PPL2 and PPM1/2 neurons,
with one synapse column per cluster. evidence.json's "targets" block maps the
evidence clusters to those columns. Picking the columns of a gene's clusters
and adding them up is all this module does: it is connectivity, not the
simulation, so it works while the engine is still a placeholder.

Target expression comes from data/combinedDatabase.csv, but only for the atlas
labels the "targets" block lists, on the FlyWire types it lists for each.
Like bio/expression.py, it is context: a type with no atlas row is "not
measured", and nothing here changes a seed, a confidence or a score. The
table's pd_score, impact and perturbation columns are a scoring proposal for
CS1 and are deliberately not read.
"""

from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd

from neurosim import config
from neurosim.models import DirectTarget, DirectTargets, TargetExpression

UNLABELLED = "unlabelled"
_FBBT = re.compile(r"FBbt_\d{8}")


def _block(table: dict) -> dict | None:
    block = table.get("targets")
    if not block or not config.DOWNSTREAM_PATH.exists():
        return None
    return block


@lru_cache(maxsize=4)
def _read_csv(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


def _csv(path) -> pd.DataFrame:
    """Read once per file version, so an edited CSV is picked up without a restart."""
    return _read_csv(str(path), path.stat().st_mtime)


def _label_key(label: str) -> str:
    """Atlas labels come with curly or straight quotes and stray spaces ("alpha' /beta'")."""
    return re.sub(r"\s*/\s*", "/", label.replace("’", "'")).strip().lower()


def fbbt_ids(label: str) -> list[str]:
    """FlyBase anatomy ids for an atlas label; a pooled label ("a ; b") gets one per part."""
    if not config.FBBT_PATH.exists():
        return []
    ids = {}
    for _, row in _csv(config.FBBT_PATH).iterrows():
        found = _FBBT.search(str(row["fbbt_id"]))  # one id has a stray letter after it
        if found:
            ids[_label_key(str(row["cluster"]))] = found.group()
    return [ids[k] for k in (_label_key(part) for part in label.split(";")) if k in ids]


def _target_expression(block: dict, table: dict, fly_genes: list[str]) -> dict[str, TargetExpression]:
    """Cell type -> atlas values for the gene's fly orthologs, trusted labels only."""
    if not config.TARGET_EXPRESSION_PATH.exists() or not fly_genes:
        return {}
    labels = block.get("atlas_labels", {})
    names = table.get("expression", {}).get("fly_gene_names", {})
    rows = _csv(config.TARGET_EXPRESSION_PATH)
    rows = rows.assign(fly_gene=rows["fly_gene"].map(lambda g: names.get(g, g)))
    rows = rows[rows["fly_gene"].isin(fly_genes) & rows["expression"].notna()]
    out: dict[str, TargetExpression] = {}
    for label, mapping in labels.items():
        hits = rows[(rows["davis_cell_type"] == label) & rows["flywire_type"].isin(mapping["cell_types"])]
        for cell_type, group in hits.groupby("flywire_type"):
            tpm = {f: round(float(v), 1) for f, v in group.groupby("fly_gene")["expression"].first().items()}
            out[str(cell_type)] = TargetExpression(tpm=tpm, atlas_label=label, match=mapping["match"],
                                                   fbbt_ids=fbbt_ids(label), note=mapping.get("_note"))
    return out


def direct_targets(human_gene: str, high_confidence_only: bool = False, table: dict | None = None,
                   top: int = config.TOP_DIRECT_TARGETS, disease: str | None = None) -> DirectTargets | None:
    """The cell types the gene's lost clusters synapse onto, most synapses first.
    None when the table is missing or no evidence row names a cluster the table
    has a column for (user-supplied cell types have none)."""
    from neurosim.bio import evidence

    table = table or evidence.load_evidence()
    block = _block(table)
    if block is None:
        return None
    clusters = list(dict.fromkeys(c for row in evidence.evidence_for(human_gene, high_confidence_only, disease)
                                  for c in row.clusters))
    if high_confidence_only:
        clusters = [c for c in clusters if evidence.cluster_cell_types(c, True)[1]]
    if not clusters:
        return None

    columns = block["cluster_columns"]
    covered = [c for c in clusters if c in columns]
    if not covered:
        return None
    downstream = _csv(config.DOWNSTREAM_PATH)
    downstream = downstream[downstream["flywire_type"] != UNLABELLED]
    # ALL_DA spans every column, so with it in the set each column counts once.
    used = list(dict.fromkeys(col for c in covered for col in columns[c]))
    synapses = downstream[used].sum(axis=1) if used else pd.Series(0, index=downstream.index)
    hit = downstream[synapses > 0].assign(synapses=synapses[synapses > 0])
    hit = hit.sort_values(["synapses", "flywire_type"], ascending=[False, True])

    entry = table["orthologs"].get(human_gene)
    fly_genes = list(entry.get("fly_genes", [])) if isinstance(entry, dict) else []
    expression = _target_expression(block, table, fly_genes)
    # Per-cluster numbers only for single-column clusters; ALL_DA would repeat the total.
    split = [c for c in covered if len(columns[c]) == 1]

    targets = [
        DirectTarget(
            cell_type=row.flywire_type,
            synapses=int(row.synapses),
            by_cluster={c: int(getattr(row, columns[c][0])) for c in split if getattr(row, columns[c][0]) > 0},
            n_neurons=int(row.n_partner_neurons),
            expression=expression.get(row.flywire_type),
        )
        for row in hit.head(top).itertuples()
    ]
    atlas = table.get("expression", {})
    return DirectTargets(
        human_gene=human_gene,
        clusters=covered,
        clusters_not_covered=[c for c in clusters if c not in columns],
        total_synapses=int(hit["synapses"].sum()),
        n_target_types=len(hit),
        targets=targets,
        n_types_with_expression=sum(1 for t in hit["flywire_type"] if t in expression),
        citation=block["citation"],
        expression_citation=atlas.get("citation") if expression else None,
        expression_url=atlas.get("url") if expression else None,
    )
