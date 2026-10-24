"""Engine tests beyond the toy table: connectome assembly, baseline statistics,
grouping, comparison and the pipeline end to end on a synthetic brain."""

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from neurosim.engine.graph import build_connectome

from engine_status import needs_engine


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


@needs_engine
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


@needs_engine
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


@needs_engine
def test_benjamini_hochberg_matches_hand_computed_values_and_skips_nan():
    from neurosim.engine.baseline import benjamini_hochberg

    q = benjamini_hochberg(np.array([0.01, 0.04, np.nan, 0.03, 0.005]))
    assert np.allclose(q[[0, 1, 3, 4]], [0.02, 0.04, 0.04, 0.02])
    assert np.isnan(q[2])


@needs_engine
def test_z_and_p_are_empirical_and_one_sided():
    from neurosim.engine.baseline import z_and_p

    null = np.array([[0.0, 1.0, 2.0, 3.0], [1.0, 1.0, 1.0, 1.0]])
    mean, sd, z, p = z_and_p(np.array([4.0, 1.0]), null)
    assert mean.tolist() == [1.5, 1.0]
    assert z[0] == pytest.approx(2.5 / np.std([0, 1, 2, 3]))
    assert p.tolist() == [1 / 5, 5 / 5]  # nothing beats 4; every draw ties 1
    assert z[1] == 0.0  # zero spread is floored, not a division by zero


@needs_engine
def test_random_draws_are_reproducible_and_without_replacement():
    from neurosim.engine.baseline import draw_random_seeds

    pool = np.arange(10, 30)
    a = draw_random_seeds(pool, 5, 50, np.random.default_rng(42))
    b = draw_random_seeds(pool, 5, 50, np.random.default_rng(42))
    assert a.shape == (50, 5) and np.array_equal(a, b)
    assert all(len(set(row)) == 5 and set(row) <= set(pool) for row in a)
    with pytest.raises(ValueError):
        draw_random_seeds(pool, 21, 1, np.random.default_rng(0))


@needs_engine
def test_synthetic_brain_is_reproducible_and_has_a_mixed_da_pool():
    from neurosim.engine.synthetic import synthetic_connectome

    a, b = synthetic_connectome(), synthetic_connectome()
    assert (a.W != b.W).nnz == 0
    da_types = set(a.neurons.loc[a.dopaminergic(), "cell_type"])
    assert {"PAM02", "PPL101", "PPM3_syn"} <= da_types
    sums = np.asarray(a.A.sum(axis=1)).ravel()
    assert np.allclose(sums[a.in_strength > 0], 1.0)


def _toy():
    from test_engine_toy import NAMES, P, toy_W

    neurons = pd.DataFrame({"cell_type": NAMES, "region": ["R1", "R0", "R1", "R1", "R1", "R2", "R2"],
                            "super_region": ["top", "top", "top", "top", "top", "bottom", "bottom"]})
    return build_connectome(toy_W(), neurons, np.arange(len(NAMES)) + 1), P


@needs_engine
def test_top_path_strength_is_the_product_of_input_fractions():
    from neurosim.engine.subgraph import top_paths_with_strength

    conn, P = _toy()
    [(path, strength)] = top_paths_with_strength(conn, [P["S"]], P["D"], k=3, hops=3)
    assert path == [P["S"], P["A"], P["B"], P["D"]]
    assert strength == pytest.approx(0.375)  # equals h3[D] in the design doc table


@needs_engine
def test_subgraph_marks_seeds_and_lost_drive():
    from neurosim.engine.perturb import initial_deficit
    from neurosim.engine.propagate import propagate
    from neurosim.engine.subgraph import neuron_subgraph
    from neurosim.models import PerturbationMode

    conn, P = _toy()
    x0 = initial_deficit(conn.n, np.array([P["S"]]), PerturbationMode.KNOCKOUT)
    prop = propagate(conn.A, x0, 3, 0.5)
    sub = neuron_subgraph(conn, prop, np.array([P["S"]]), max_nodes=10, x0=x0)
    nodes = {n.label: n for n in sub.nodes}
    assert set(nodes) == {"S", "A", "B", "D"}  # seeds plus every neuron with impact > 0
    assert nodes["S"].is_seed and not nodes["A"].is_seed
    label = {n.id: n.label for n in sub.nodes}
    edges = {(label[e.source], label[e.target]): e for e in sub.edges}
    assert edges[("S", "A")].lost == pytest.approx(0.75)
    assert edges[("A", "B")].lost == pytest.approx(0.5 * 0.75)
    assert all(0 <= n.x <= 1000 and 0 <= n.y <= 1000 for n in sub.nodes)


def test_comparison_uses_z_scores_and_a_template_summary():
    from neurosim.api import mocks
    from neurosim.engine.compare import compare_runs
    from neurosim.models import GroupLevel, SimulationRequest

    def run(gene, zs, hits):
        result = mocks.mock_result(SimulationRequest(human_gene=gene))
        groups = [mocks._group(name, z, None).model_copy(update={"above_chance": name in hits})
                  for name, z in zs.items()]
        return result.model_copy(update={"run_id": gene, "groups": {GroupLevel.SUPER_REGION: groups}})

    a = run("PINK1", {"mb": 5.0, "lh": 3.0, "cx": 1.0, "ol": -1.0}, {"mb", "lh"})
    b = run("PRKN", {"mb": 4.0, "lh": 0.5, "cx": 2.0, "ol": -2.0}, {"mb", "cx"})
    c = compare_runs(a, b, GroupLevel.SUPER_REGION)
    assert c.spearman_rho == pytest.approx(0.8)
    assert (c.shared_top, c.only_a, c.only_b) == (["mb"], ["lh"], ["cx"])
    assert c.summary.startswith("PINK1 and PRKN hit similar brain areas (rank correlation 0.80 over 4).")
