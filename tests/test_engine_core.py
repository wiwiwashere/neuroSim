"""Engine tests beyond the toy table: connectome assembly, baseline statistics,
grouping, comparison and the pipeline end to end on a synthetic brain."""

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from neurosim.engine.graph import build_connectome


def small_connectome():
    W = sp.csr_matrix(np.array([[0, 6, 0], [0, 0, 8], [0, 0, 0]], dtype=float))
    neurons = pd.DataFrame({"cell_type": ["PAM01", "KC", "MBON01"], "nt_type": ["DA", "ACH", None]})
    return build_connectome(W, neurons, np.array([101, 102, 103]))


def test_positions_follow_root_ids_and_reject_unknown_ids():
    conn = small_connectome()
    assert conn.positions([103, 101]).tolist() == [2, 0]
    with pytest.raises(KeyError):
        conn.positions([101, 999])


def test_dopaminergic_pool_reads_nt_type():
    assert small_connectome().dopaminergic().tolist() == [0]


def test_impact_never_exceeds_the_design_bound():
    from neurosim.engine.graph import input_normalize
    from neurosim.engine.propagate import propagate

    rng = np.random.default_rng(0)
    W = sp.random(300, 300, density=0.05, random_state=1, data_rvs=lambda k: rng.integers(5, 50, k)).tocsr()
    A, _ = input_normalize(W)
    x0 = np.zeros((300, 4))
    x0[rng.choice(300, 40, replace=False), :] = 1.0
    prop = propagate(A, x0, hops=3, decay=0.5)
    assert all(h.max() <= 1.0 + 1e-12 for h in prop.per_hop)
    assert prop.impact.max() <= 1.75 + 1e-12


def test_batched_group_means_match_group_table():
    from neurosim.engine.graph import input_normalize
    from neurosim.engine.propagate import propagate
    from neurosim.engine.vulnerability import group_codes, group_means_batch, group_table
    from neurosim.models import GroupLevel

    rng = np.random.default_rng(3)
    W = sp.random(200, 200, density=0.05, random_state=2, data_rvs=lambda k: rng.integers(5, 50, k)).tocsr()
    A, _ = input_normalize(W)
    neurons = pd.DataFrame({"region": rng.choice(["R1", "R2", "R3", None], 200)})
    x0 = np.zeros(200)
    x0[[1, 5, 9]] = 1.0
    prop = propagate(A, x0, 3, 0.5)
    codes, names = group_codes(neurons, GroupLevel.REGION)
    batch = group_means_batch(prop.impact, prop.seed_mask, codes, len(names))[:, 0]
    table = group_table(prop, neurons, GroupLevel.REGION, 5, 0.1).set_index("group")
    for i, name in enumerate(names):
        assert batch[i] == pytest.approx(table.loc[name, "mean_impact"])
    assert not table.loc["unlabelled", "rankable"]
