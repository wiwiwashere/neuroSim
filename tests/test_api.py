"""HTTP-level behaviour of the FastAPI app: mocks or the real pipeline depending
on the startup flags, and how errors reach the browser."""

import importlib

import pytest
from fastapi.testclient import TestClient

from neurosim.engine import pipeline
from neurosim.engine.graph import set_connectome

from engine_status import needs_engine


def client_with(monkeypatch, **env) -> TestClient:
    for key in ("NEUROSIM_MOCKS", "NEUROSIM_SYNTHETIC"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import neurosim.api.main as main

    return TestClient(importlib.reload(main).app)


@pytest.fixture(autouse=True)
def reset_engine():
    yield
    set_connectome(None)
    pipeline.clear_cache()


def test_mock_flag_serves_sample_payloads(monkeypatch):
    client = client_with(monkeypatch, NEUROSIM_MOCKS="1")
    assert client.post("/simulate", json={"human_gene": "PRKN"}).json()["run_id"].startswith("mock-")


def test_defaults_to_mocks_without_processed_data(monkeypatch, tmp_path):
    from neurosim import config

    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    client = client_with(monkeypatch)
    assert client.post("/simulate", json={"human_gene": "PRKN"}).json()["run_id"].startswith("mock-")



def test_stays_on_mocks_while_the_engine_is_a_placeholder(monkeypatch):
    import neurosim.engine.graph as graph

    monkeypatch.setattr(graph, "processed_data_available", lambda: True)
    monkeypatch.setattr(graph, "connectome_available", lambda: False)   # fake seeds: there are no files behind the lie above
    monkeypatch.setattr(pipeline, "engine_ready", lambda: False)
    client = client_with(monkeypatch)
    assert client.post("/simulate", json={"human_gene": "PRKN"}).json()["run_id"].startswith("mock-")


@needs_engine
def test_synthetic_flag_runs_the_real_pipeline_end_to_end(monkeypatch):
    client = client_with(monkeypatch, NEUROSIM_SYNTHETIC="1")
    assert client.get("/diseases").json() == ["parkinsons"]
    genes = {g["human_gene"]: g for g in client.get("/diseases/parkinsons/genes").json()}
    assert genes["SNCA"]["simulatable"] is False
    assert client.get("/genes/PRKN/chain").json()["seed_types"]

    run = client.post("/simulate", json={"human_gene": "PRKN"}).json()
    run_id = run["run_id"]
    assert not run_id.startswith("mock-") and run["groups"]["super_region"]
    assert client.get(f"/runs/{run_id}").json()["run_id"] == run_id
    assert client.get(f"/runs/{run_id}/sankey").json()
    assert client.get(f"/runs/{run_id}/subgraph").json()["nodes"]
    neuron = run["top_neurons"][0]["root_id"]
    assert client.get(f"/runs/{run_id}/neurons/{neuron}/explain").json()["paths"]
    other = client.post("/simulate", json={"human_gene": "LRRK2"}).json()["run_id"]
    assert "summary" in client.get("/compare", params={"run_a": run_id, "run_b": other}).json()


def test_seed_problems_are_422_and_unknown_runs_404(monkeypatch):
    client = client_with(monkeypatch, NEUROSIM_SYNTHETIC="1")
    response = client.post("/simulate", json={"human_gene": "SNCA"})
    assert response.status_code == 422 and "no fly ortholog" in response.json()["detail"]
    assert client.get("/runs/nope").status_code == 404


def test_unhandled_error_is_json_with_a_readable_detail(monkeypatch):
    from neurosim.agent import agent

    def boom(*args):
        raise RuntimeError("bug")

    monkeypatch.setattr(agent, "chat", boom)
    client = TestClient(client_with(monkeypatch, NEUROSIM_MOCKS="1").app, raise_server_exceptions=False)
    res = client.post("/agent/chat", json={"message": "Test PPL101 alone"})
    assert res.status_code == 500
    assert res.json() == {"detail": "neuroSim hit an internal error (RuntimeError). The API log has the traceback."}


def test_mock_dynamics_endpoint(monkeypatch):
    client = client_with(monkeypatch, NEUROSIM_MOCKS="1")
    run_id = client.post("/simulate", json={"human_gene": "PRKN"}).json()["run_id"]
    series = client.get(f"/runs/{run_id}/dynamics").json()
    assert series["run_id"] == run_id
    assert series["model"] == "WCModel"
    assert len(series["frames"]) == 60
    assert series["frames"][0]["seed_health"] == 1.0
    assert series["frames"][-1]["seed_health"] == 0.0


def test_expression_endpoint_works_for_genes_without_evidence(monkeypatch):
    client = client_with(monkeypatch, NEUROSIM_MOCKS="1")
    gba = client.get("/genes/GBA1/expression").json()
    assert gba["fly_genes"] == ["Gba1a", "Gba1b"] and gba["clusters_measured"] == ["PAM"]
    assert client.get("/genes/SNCA/expression").json() is None
