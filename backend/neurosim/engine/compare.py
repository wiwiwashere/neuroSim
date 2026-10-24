"""Comparisons between runs (CS1). See docs/ENGINE_DESIGN.md, section 8.

The headline question for the demo: "do PINK1 and PRKN hit the same circuits?"

Compare two SimulationResults at one group level:
    spearman_rho   correlation of the two groups' z-scores over groups rankable
                   in both runs. Near 1 = same circuits, near 0 = unrelated.
    shared_top     groups above chance in BOTH runs
    only_a/only_b  above chance in just one

Why z-scores, not raw impact: raw impact scales with seed-set size. PINK1 and
PRKN seed different numbers of neurons, so raw scores are not comparable;
z-scores against each run's own size-matched null are.

The summary sentence is built from these numbers by a template, never by the
LLM, so it cannot overstate the result.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr

from neurosim.models import Comparison, GroupLevel, SimulationResult

LEVEL_NOUN = {
    GroupLevel.REGION: "brain regions",
    GroupLevel.SUPER_REGION: "brain areas",
    GroupLevel.CELL_TYPE: "cell types",
    GroupLevel.SUPER_CLASS: "neuron classes",
}


def compare_runs(a: SimulationResult, b: SimulationResult, level: GroupLevel, top_n: int = 10) -> Comparison:
    za = {g.group: g.z_score for g in a.groups.get(level, [])}
    zb = {g.group: g.z_score for g in b.groups.get(level, [])}
    common = sorted(set(za) & set(zb))
    rho = float("nan")
    if len(common) >= 3:
        rho = float(spearmanr([za[g] for g in common], [zb[g] for g in common]).statistic)
    rho = 0.0 if np.isnan(rho) else rho

    def hits(result: SimulationResult) -> list[str]:
        return [g.group for g in result.groups.get(level, []) if g.above_chance]

    hits_a, hits_b = hits(a), hits(b)
    shared = [g for g in hits_a if g in hits_b][:top_n]
    only_a = [g for g in hits_a if g not in hits_b][:top_n]
    only_b = [g for g in hits_b if g not in hits_a][:top_n]
    return Comparison(run_a=a.run_id, run_b=b.run_id, level=level, spearman_rho=round(rho, 3),
                      shared_top=shared, only_a=only_a, only_b=only_b,
                      summary=_summary(a.request.human_gene, b.request.human_gene, level, rho, len(common), shared,
                                       only_a, only_b))


def _summary(gene_a: str, gene_b: str, level: GroupLevel, rho: float, n_common: int, shared: list[str],
             only_a: list[str], only_b: list[str]) -> str:
    noun = LEVEL_NOUN[level]
    if n_common < 3:
        return f"{gene_a} and {gene_b} have too few {noun} ranked in both runs to compare."
    reading = "similar" if rho >= 0.6 else "partly similar" if rho >= 0.3 else "different"
    parts = [f"{gene_a} and {gene_b} hit {reading} {noun} (rank correlation {rho:.2f} over {n_common})."]
    if shared:
        parts.append(f"Both are above chance in {_join(shared)}.")
    else:
        parts.append(f"No {noun} are above chance in both.")
    if only_a or only_b:
        parts.append(f"Only {gene_a}: {_join(only_a) or 'none'}. Only {gene_b}: {_join(only_b) or 'none'}.")
    return " ".join(parts)


def _join(items: list[str], limit: int = 3) -> str:
    shown = items[:limit]
    more = f" and {len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(shown) + more


def leave_one_cluster_out(request) -> list[dict]:
    """Stretch ("find the bottleneck"): rerun the request once per seed cluster
    with that cluster removed, and report how much the top groups' z-scores
    drop. The cluster whose removal drops them most carries the effect.
    The agent's follow-up experiment calls this."""
    from neurosim.engine import pipeline

    level = GroupLevel.SUPER_REGION
    base = pipeline.run_simulation(request)
    top = [g for g in base.groups.get(level, [])][:5]
    clusters: dict[str, list[str]] = {}
    for seed_type in base.seeds.seed_types:
        clusters.setdefault(seed_type.cluster, []).append(seed_type.cell_type)
    results = []
    for cluster, cell_types in clusters.items():
        rest = [t for c, types in clusters.items() if c != cluster for t in types]
        if not rest:
            results.append({"cluster": cluster, "n_cell_types": len(cell_types), "mean_z_drop": None,
                            "note": "only seed cluster; removing it leaves nothing to simulate"})
            continue
        run = pipeline.run_simulation(request.model_copy(update={"seed_cell_types": rest}))
        z_after = {g.group: g.z_score for g in run.groups.get(level, [])}
        drops = {g.group: g.z_score - z_after[g.group] for g in top if g.group in z_after}
        results.append({"cluster": cluster, "n_cell_types": len(cell_types), "run_id": run.run_id,
                        "mean_z_drop": round(float(np.mean(list(drops.values()))), 3) if drops else None,
                        "z_drop_by_group": {k: round(v, 3) for k, v in drops.items()}})
    return sorted(results, key=lambda r: -(r["mean_z_drop"] if r["mean_z_drop"] is not None else -np.inf))
