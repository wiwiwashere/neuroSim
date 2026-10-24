"""FastAPI app (CS2). Run: uvicorn neurosim.api.main:app --reload

Every endpoint is a thin wrapper over engine/pipeline.py or bio/evidence.py.
No science happens here. While NEUROSIM_MOCKS=1 (the default until the engine
works) endpoints return api/mocks.py payloads so the frontend is never blocked.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from neurosim.api import mocks
from neurosim.models import Comparison, GroupLevel, SankeyLink, SimulationRequest, SimulationResult, Subgraph

USE_MOCKS = os.environ.get("NEUROSIM_MOCKS", "1") == "1"

app = FastAPI(title="neuroSim")


@app.get("/diseases")
def diseases() -> list[str]:
    """Diseases in the evidence table (just Parkinson's for the MVP)."""
    if USE_MOCKS:
        return ["parkinsons"]
    raise NotImplementedError  # bio.evidence.list_diseases()


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
    raise NotImplementedError  # bio.evidence.list_genes(disease)


@app.get("/genes/{human_gene}/chain")
def mapping_chain(human_gene: str, high_confidence_only: bool = False) -> dict:
    """Everything for the mapping-chain screen: ortholog, evidence rows,
    clusters, cell types, neuron counts, confidence at every link."""
    if USE_MOCKS:
        return mocks.mock_seeds(human_gene).model_dump()
    raise NotImplementedError  # bio.evidence.resolve_seeds(...)


@app.post("/simulate")
def simulate(request: SimulationRequest) -> SimulationResult:
    """Run (or fetch from cache) one experiment."""
    if USE_MOCKS:
        return mocks.mock_result(request)
    raise NotImplementedError  # pipeline.run_simulation(request)


@app.get("/runs/{run_id}")
def run(run_id: str) -> SimulationResult:
    if USE_MOCKS:
        return mocks.mock_result()
    raise NotImplementedError  # pipeline.get_result(run_id)


@app.get("/runs/{run_id}/sankey")
def sankey(run_id: str) -> list[SankeyLink]:
    if USE_MOCKS:
        return mocks.mock_sankey()
    raise NotImplementedError  # pipeline.get_sankey(run_id)


@app.get("/runs/{run_id}/subgraph")
def subgraph(run_id: str) -> Subgraph:
    if USE_MOCKS:
        return mocks.mock_subgraph()
    raise NotImplementedError  # pipeline.get_subgraph(run_id)


@app.get("/runs/{run_id}/neurons/{root_id}/explain")
def explain(run_id: str, root_id: int) -> dict:
    if USE_MOCKS:
        return {"root_id": root_id, "paths": [{"neurons": ["PPL101", "MBON01"], "strength": 0.41}]}
    raise NotImplementedError  # pipeline.explain_neuron(run_id, root_id)


@app.get("/compare")
def compare(run_a: str, run_b: str, level: GroupLevel = GroupLevel.REGION) -> Comparison:
    if USE_MOCKS:
        return mocks.mock_comparison()
    raise NotImplementedError  # pipeline.compare(run_a, run_b, level)


@app.post("/agent/chat")
def agent_chat(body: dict) -> dict:
    """{"messages": [...]} in, {"reply": str, "tool_calls": [...], "run_ids": [...]} out.
    The frontend shows tool_calls so users see the agent used real results."""
    raise NotImplementedError  # agent.agent.chat(body["messages"])
