"""Tests for the offline prep (prep/build_dataset.py) on a tiny fake FlyWire
table. The real run is checked by its printed summary, not here."""

import pandas as pd

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
