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

from neurosim.models import Comparison, GroupLevel, SimulationResult


def compare_runs(a: SimulationResult, b: SimulationResult, level: GroupLevel, top_n: int = 10) -> Comparison:
    raise NotImplementedError


def leave_one_cluster_out(request) -> list[dict]:
    """Stretch ("find the bottleneck"): rerun the request once per seed cluster
    with that cluster removed, and report how much the top groups' z-scores
    drop. The cluster whose removal drops them most carries the effect.
    The agent's follow-up experiment calls this."""
    raise NotImplementedError
