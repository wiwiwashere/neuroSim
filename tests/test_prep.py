"""Tests for the offline prep (prep/build_dataset.py) on a tiny fake FlyWire
table. The real run is checked by its printed summary, not here."""

import numpy as np
import pandas as pd
import pytest

from neurosim.prep import build_dataset as bd

# Neuron 1 is dopaminergic, 2 is cholinergic, 9 and 8 only receive input.
# Pair 1->9 has 3 + 3 synapses in two neuropils (kept, 6). Pair 2->8 has
# 2 + 2 (dropped, 4). Pair 2->9 has 5 in one neuropil (kept).
ROWS = [
    # pre, post, neuropil, syn, ach, da
    (1, 9, "MB_CA_R", 3, 0.1, 0.9),
    (1, 9, "MB_ML_R", 3, 0.1, 0.9),
    (2, 8, "LH_R", 2, 0.8, 0.0),
    (2, 8, "SLP_R", 2, 0.8, 0.0),
    (2, 9, "MB_ML_R", 5, 0.8, 0.0),
]


def fake_conn() -> pd.DataFrame:
    pre, post, neuropil, syn, ach, da = zip(*ROWS)
    df = pd.DataFrame({bd.PRE: pre, bd.POST: post, "neuropil": neuropil, "syn_count": syn})
    for col in bd.NT_COLUMNS:
        df[col] = 0.0
    df["ach_avg"], df["da_avg"] = ach, da
    for col in ("gaba_avg", "glut_avg", "oct_avg", "ser_avg"):
        df[col] = (1.0 - df["ach_avg"] - df["da_avg"]) / 4
    return df


def test_aggregate_pairs_sums_then_thresholds():
    pairs = bd.aggregate_pairs(fake_conn(), threshold=5)
    assert pairs[["pre", "post", "syn_count"]].values.tolist() == [[1, 9, 6], [2, 9, 5]]


def test_primary_input_region_uses_all_input_before_threshold():
    region = bd.primary_input_region(fake_conn())
    # 9 gets 3 (MB_CA_R) + 3 + 5 (MB_ML_R); 8 gets 2 + 2, tie broken alphabetically.
    assert region.to_dict() == {8: "LH_R", 9: "MB_ML_R"}


def test_neuron_transmitter_is_synapse_weighted():
    nt = bd.neuron_transmitter(fake_conn())
    assert nt.loc[1, "nt_type"] == "DA"
    assert nt.loc[1, "nt_type_score"] == pytest.approx(0.9)
    assert nt.loc[2, "nt_type"] == "ACH"
    assert 9 not in nt.index  # no output synapses, no vote


def test_neuron_transmitter_skips_rows_without_prediction():
    conn = fake_conn()
    conn.loc[len(conn)] = {**conn.iloc[0].to_dict(), bd.PRE: 3, "syn_count": 7}
    conn.loc[len(conn) - 1, list(bd.NT_COLUMNS)] = np.nan
    conn.loc[0, list(bd.NT_COLUMNS)] = np.nan  # one of neuron 1's two rows
    nt = bd.neuron_transmitter(conn)
    assert 3 not in nt.index
    assert nt.loc[1, "nt_type"] == "DA" and nt.loc[1, "nt_type_score"] == pytest.approx(0.9)


def test_build_matrix_follows_root_id_order():
    pairs = bd.aggregate_pairs(fake_conn(), threshold=5)
    root_ids = np.array([1, 2, 8, 9])
    W = bd.build_matrix(pairs, root_ids)
    assert W.shape == (4, 4)
    assert W[0, 3] == 6 and W[1, 3] == 5 and W.nnz == 2


def test_build_matrix_rejects_unknown_ids():
    pairs = pd.DataFrame({"pre": [1], "post": [7], "syn_count": [5]})
    with pytest.raises(ValueError):
        bd.build_matrix(pairs, np.array([1, 2]))
