"""FastAPI app (CS2). Run: uvicorn neurosim.api.main:app --reload

Every endpoint is a thin wrapper over engine/pipeline.py or bio/evidence.py.
No science happens here.

Data source, decided once at startup:
    NEUROSIM_MOCKS=1        api/mocks.py payloads (fake numbers, "mock-" run IDs)
    NEUROSIM_MOCKS=0        the real pipeline on data/processed
    unset                   real pipeline once data/processed exists AND the
                            engine is implemented (pipeline.engine_ready), else mocks
    NEUROSIM_SYNTHETIC=1    the real pipeline on the made-up test brain
                            (engine/synthetic.py), handy before prep has run
"""

from __future__ import annotations

import os
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException

from neurosim.api import mocks
from neurosim.bio import evidence
from neurosim.engine import pipeline
from neurosim.engine.graph import processed_data_available, set_connectome
from neurosim.models import Comparison, GroupLevel, SankeyLink, SimulationRequest, SimulationResult, Subgraph

USE_SYNTHETIC = os.environ.get("NEUROSIM_SYNTHETIC") == "1"
_MOCKS_ENV = os.environ.get("NEUROSIM_MOCKS")
if USE_SYNTHETIC:
    USE_MOCKS = False
elif _MOCKS_ENV is not None:
    USE_MOCKS = _MOCKS_ENV == "1"
else:
    USE_MOCKS = not (processed_data_available() and pipeline.engine_ready())

if USE_SYNTHETIC:
    from neurosim.engine.synthetic import synthetic_connectome

    set_connectome(synthetic_connectome())

app = FastAPI(title="neuroSim")


@contextmanager
def _http_errors():
    """Seed problems are the user's to fix (422, message shown as is);
    unknown run or neuron IDs are 404."""
    try:
        yield
    except evidence.SeedError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"not found: {e}") from e


@app.get("/diseases")
def diseases() -> list[str]:
    """Diseases in the evidence table (just Parkinson's for the MVP)."""
    if USE_MOCKS:
        return ["parkinsons"]
    return evidence.list_diseases()


@app.get("/diseases/{disease}/genes")
def genes(disease: str) -> list[dict]:
    """Gene picker: gene, fly ortholog, confidence, whether it can be simulated."""
    if USE_MOCKS:
        return [
            {"human_gene": "PINK1", "fly_genes": ["Pink1"], "best_tier": "medium", "simulatable": True},
            {"human_gene": "PRKN", "fly_genes": ["park"], "best_tier": "medium", "simulatable": True},
            {"human_gene": "PARK7", "fly_genes": ["dj-1beta", "DJ-1alpha"], "best_tier": "low", "simulatable": True},
            {"human_gene": "LRRK2", "fly_genes": ["Lrrk"], "best_tier": "low", "simulatable": True},
            {"human_gene": "SNCA", "fly_genes": [], "best_tier": None, "simulatable": False},
        ]
    return evidence.list_genes(disease)


@app.get("/genes/{human_gene}/chain")
def mapping_chain(human_gene: str, high_confidence_only: bool = False) -> dict:
    """Everything for the mapping-chain screen: ortholog, evidence rows,
    clusters, cell types, neuron counts, confidence at every link."""
    if USE_MOCKS:
        return mocks.mock_seeds(human_gene).model_dump()
    with _http_errors():
        return evidence.resolve_seeds(
            SimulationRequest(human_gene=human_gene, high_confidence_only=high_confidence_only)
        ).model_dump()


@app.post("/simulate")
def simulate(request: SimulationRequest) -> SimulationResult:
    """Run (or fetch from cache) one experiment."""
    if USE_MOCKS:
        return mocks.mock_result(request)
    with _http_errors():
        return pipeline.run_simulation(request)


@app.get("/runs/{run_id}")
def run(run_id: str) -> SimulationResult:
    if USE_MOCKS:
        return mocks.mock_result()
    with _http_errors():
        return pipeline.get_result(run_id)


@app.get("/runs/{run_id}/sankey")
def sankey(run_id: str) -> list[SankeyLink]:
    if USE_MOCKS:
        return mocks.mock_sankey()
    with _http_errors():
        return pipeline.get_sankey(run_id)


@app.get("/runs/{run_id}/subgraph")
def subgraph(run_id: str) -> Subgraph:
    if USE_MOCKS:
        return mocks.mock_subgraph()
    with _http_errors():
        return pipeline.get_subgraph(run_id)


@app.get("/runs/{run_id}/neurons/{root_id}/explain")
def explain(run_id: str, root_id: int) -> dict:
    if USE_MOCKS:
        return {"root_id": root_id, "paths": [{"neurons": ["PPL101", "MBON01"], "strength": 0.41}]}
    with _http_errors():
        return pipeline.explain_neuron(run_id, root_id)


@app.get("/compare")
def compare(run_a: str, run_b: str, level: GroupLevel = GroupLevel.REGION) -> Comparison:
    if USE_MOCKS:
        return mocks.mock_comparison()
    with _http_errors():
        return pipeline.compare(run_a, run_b, level)


@app.post("/agent/chat")
def agent_chat(body: dict) -> dict:
    """{"message": str, "interaction_id": str | None} in,
    {"reply": str, "tool_calls": [...], "run_ids": [...], "interaction_id": str} out.
    The frontend keeps only the latest interaction_id (Gemini holds the history)
    and shows tool_calls so users see the agent used real results."""
    raise NotImplementedError  # agent.agent.chat(body["message"], body.get("interaction_id"))
