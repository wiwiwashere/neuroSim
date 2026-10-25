"""Kait's one-hop table as direct targets of a gene's lost clusters, with
atlas expression only where the label mapping is trusted."""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from neurosim import config
from neurosim.bio import evidence, targets


def test_prkn_targets_are_the_ppl1_column_most_synapses_first():
    prkn = targets.direct_targets("PRKN")
    table = pd.read_csv(config.DOWNSTREAM_PATH)
    ppl1 = table[(table["syn_from_PPL1"] > 0) & (table["flywire_type"] != "unlabelled")]
    assert prkn.clusters == ["PPL1"] and prkn.clusters_not_covered == []
    assert prkn.n_target_types == len(ppl1) and prkn.total_synapses == ppl1["syn_from_PPL1"].sum()
    assert [t.cell_type for t in prkn.targets[:4]] == ["KCg-m", "KCapbp-m", "APL", "DPM"]
    assert prkn.targets[0].synapses == 5476 and prkn.targets[0].by_cluster == {"PPL1": 5476}
    assert len(prkn.targets) == config.TOP_DIRECT_TARGETS
    synapses = [t.synapses for t in prkn.targets]
    assert synapses == sorted(synapses, reverse=True)


def test_clusters_add_up_and_ppm3_is_reported_as_not_covered():
    pink1 = targets.direct_targets("PINK1")   # Wang 2006: PAL, PPM1/2, PPM3, PPL2
    assert set(pink1.clusters) == {"PAL", "PPM1/2", "PPL2"} and pink1.clusters_not_covered == ["PPM3"]
    for t in pink1.targets:
        assert sum(t.by_cluster.values()) == t.synapses
    # PPM3 is an inferred match, so the high-confidence view drops it instead of flagging it.
    assert targets.direct_targets("PINK1", high_confidence_only=True).clusters_not_covered == []


def test_all_da_counts_each_column_once():
    park7 = targets.direct_targets("PARK7")
    table = pd.read_csv(config.DOWNSTREAM_PATH).set_index("flywire_type")
    assert park7.clusters == ["ALL_DA"]
    assert park7.targets[0].synapses == table.loc[park7.targets[0].cell_type, "syn_from_seeds"]
    assert park7.targets[0].by_cluster == {}


def test_target_expression_uses_trusted_labels_only():
    lrrk2 = {t.cell_type: t for t in targets.direct_targets("LRRK2", top=2000).targets}
    assert lrrk2["KCab-p"].expression.tpm == {"Lrrk": 45.0}
    assert lrrk2["KCab-p"].expression.match == "exact"
    assert lrrk2["KCab-p"].expression.fbbt_ids == ["FBbt_00110931"]
    # The MBON label pools the MBON10 and MBON11 drivers only.
    assert lrrk2["MBON11"].expression.match == "coarse"
    assert lrrk2["MBON12"].expression is None
    # The centrifugal rows are mapped to the wrong neurons, so they are never read.
    centrifugal = {"cL14", "cL16", "cL21", "cL22b", "LT39", "LT41", "LT56", "cML01", "OA-ASM1"}
    assert all(lrrk2[t].expression is None for t in centrifugal if t in lrrk2)
    # Big targets the atlas never profiled are "not measured".
    assert lrrk2["KCg-m"].expression is None and lrrk2["APL"].expression is None


def test_fly_gene_spellings_follow_the_ortholog_table():
    park7 = {t.cell_type: t for t in targets.direct_targets("PARK7").targets}
    assert set(park7["KCapbp-m"].expression.tpm) == {"dj-1beta", "DJ-1alpha"}


def test_fbbt_ids_tolerate_quotes_spaces_and_stray_letters():
    assert targets.fbbt_ids("alpha’/beta’ middle Kenyon cell") == ["FBbt_00100253"]
    assert targets.fbbt_ids("alpha’/beta’ anterior-posterior Kenyon cell") == ["FBbt_00100250"]


def test_no_targets_without_a_named_cluster_or_the_table(monkeypatch):
    assert targets.direct_targets("VPS35") is None    # ortholog, no evidence row yet
    assert targets.direct_targets("SNCA") is None     # the validation row is not a gene seed
    monkeypatch.setattr(config, "DOWNSTREAM_PATH", config.ROOT / "data" / "no-such-table.csv")
    assert targets.direct_targets("PRKN") is None


def test_endpoint(monkeypatch):
    monkeypatch.setenv("NEUROSIM_MOCKS", "1")
    import importlib

    import neurosim.api.main as main

    client = TestClient(importlib.reload(main).app)
    body = client.get("/genes/PRKN/targets").json()
    assert body["targets"][0]["cell_type"] == "KCg-m"
    assert client.get("/genes/VPS35/targets").json() is None


def test_cluster_columns_exist_for_every_exact_cluster():
    block = evidence.load_evidence()["targets"]
    columns = set(pd.read_csv(config.DOWNSTREAM_PATH).columns)
    assert all(col in columns for cols in block["cluster_columns"].values() for col in cols)
