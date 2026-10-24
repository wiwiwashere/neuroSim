"""Toy-graph tests for the engine (CS1). These are the definition of "done"
for each engine function: they fail with NotImplementedError until you fill
the stubs in, then they must pass.

The graph and every expected number are explained in
docs/ENGINE_DESIGN.md, section 5:

    S -30-> A <-10- X
            |20
            v
    C -20-> B -10-> D
    S -4-> E (dropped, below 5 synapses)     X -10-> E
"""

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from neurosim.engine.graph import input_normalize
from neurosim.engine.perturb import initial_deficit
from neurosim.engine.propagate import propagate
from neurosim.engine.vulnerability import disruption_score, group_table
from neurosim.models import GroupLevel, PerturbationMode
from neurosim.prep.build_dataset import aggregate_pairs

from engine_status import needs_engine

NAMES = ["S", "X", "A", "C", "B", "D", "E"]
P = {name: i for i, name in enumerate(NAMES)}
EDGES = [("S", "A", 30), ("X", "A", 10), ("A", "B", 20), ("C", "B", 20), ("B", "D", 10), ("X", "E", 10)]


def toy_W() -> sp.csr_matrix:
    rows = [P[a] for a, _, _ in EDGES]
    cols = [P[b] for _, b, _ in EDGES]
    vals = [w for _, _, w in EDGES]
    return sp.csr_matrix((vals, (rows, cols)), shape=(len(NAMES), len(NAMES)), dtype=float)


def knockout_S(hops=3, decay=0.5):
    A, _ = input_normalize(toy_W())
    x0 = initial_deficit(len(NAMES), np.array([P["S"]]), PerturbationMode.KNOCKOUT)
    return propagate(A, x0, hops=hops, decay=decay)


def test_threshold_applies_after_summing_neuropils():
    raw = pd.DataFrame(
        {
            "pre_pt_root_id": [1, 1, 2, 2],
            "post_pt_root_id": [9, 9, 8, 8],
            "neuropil": ["MB_CA_R", "MB_ML_R", "LH_R", "SLP_R"],
            "syn_count": [3, 3, 2, 2],  # pair 1->9 totals 6 (kept); 2->8 totals 4 (dropped)
        }
    )
    pairs = aggregate_pairs(raw)
    assert len(pairs) == 1
    assert pairs.iloc[0]["syn_count"] == 6


@needs_engine
def test_rows_of_A_sum_to_one_or_zero():
    A, in_strength = input_normalize(toy_W())
    sums = np.asarray(A.sum(axis=1)).ravel()
    assert np.allclose(sums[in_strength > 0], 1.0)
    assert np.allclose(sums[in_strength == 0], 0.0)
    assert A[P["A"], P["S"]] == pytest.approx(0.75)


@needs_engine
def test_toy_hops_match_design_doc():
    prop = knockout_S()
    h1, h2, h3 = prop.per_hop
    assert h1[P["A"]] == pytest.approx(0.75)
    assert h2[P["B"]] == pytest.approx(0.375)
    assert h3[P["D"]] == pytest.approx(0.375)
    assert prop.impact[P["A"]] == pytest.approx(0.75)
    assert prop.impact[P["B"]] == pytest.approx(0.1875)
    assert prop.impact[P["D"]] == pytest.approx(0.09375)
    assert prop.impact[P["E"]] == 0.0  # the 4-synapse edge was never in the graph


@needs_engine
def test_reduce_output_is_exactly_proportional():
    A, _ = input_normalize(toy_W())
    seeds = np.array([P["S"]])
    full = propagate(A, initial_deficit(len(NAMES), seeds, PerturbationMode.KNOCKOUT), 3, 0.5)
    half = propagate(A, initial_deficit(len(NAMES), seeds, PerturbationMode.REDUCE_OUTPUT, 0.5), 3, 0.5)
    assert np.allclose(half.impact, 0.5 * full.impact)


@needs_engine
def test_batched_propagation_matches_single_runs():
    A, _ = input_normalize(toy_W())
    x0 = np.zeros((len(NAMES), 2))
    x0[P["S"], 0] = 1.0
    x0[P["C"], 1] = 1.0
    batch = propagate(A, x0, 3, 0.5)
    single = knockout_S()
    assert np.allclose(batch.impact[:, 0], single.impact)


@needs_engine
def test_empty_seed_set_is_an_error():
    with pytest.raises(ValueError):
        initial_deficit(len(NAMES), np.array([], dtype=int), PerturbationMode.KNOCKOUT)


@needs_engine
def test_group_mean_excludes_seeds():
    prop = knockout_S()
    neurons = pd.DataFrame({"region": ["R1", "R0", "R1", "R1", "R1", "R2", "R2"]}, index=range(len(NAMES)))
    table = group_table(prop, neurons, GroupLevel.REGION, min_size=1, strong_hit=0.10).set_index("group")
    # R1 non-seed members: A, C, B -> (0.75 + 0 + 0.1875) / 3. S is in R1 but excluded as a seed.
    assert table.loc["R1", "mean_impact"] == pytest.approx(0.3125)
    assert table.loc["R1", "n_strong_hits"] == 1  # only A has direct >= 0.10


@needs_engine
def test_disruption_score_matches_design_doc():
    A, in_strength = input_normalize(toy_W())
    prop = knockout_S()
    # (40*0.75 + 40*0.1875 + 10*0.09375) / ((40+40+10+10) * 1.75)
    assert disruption_score(prop, in_strength, hops=3, decay=0.5) == pytest.approx(38.4375 / 175)
