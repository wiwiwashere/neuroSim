"""FastAPI app (CS2). Run from backend/:
    uvicorn neurosim.api.main:app --reload --reload-dir neurosim --reload-exclude 'neurosim/prep/*'
(prep/ is excluded: dataset edits would restart the API mid-request; see README).

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

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from neurosim import config
from neurosim.agent import agent, papers, summary
from neurosim.agent.gemini import GeminiUnavailable
from neurosim.api import mocks
from neurosim.bio import evidence
from neurosim.engine import pipeline
from neurosim.engine.graph import processed_data_available, set_connectome
from neurosim.models import Comparison, GroupLevel, SankeyLink, SimulationRequest, SimulationResult, Subgraph

USE_MOCKS = config.USE_MOCKS

app = FastAPI(title="neuroSim")


@app.exception_handler(Exception)
async def _unhandled(request: Request, err: Exception) -> JSONResponse:
    """Any bug becomes a JSON 500 with a readable detail (the traceback still
    goes to the API log), so a plain-text 500 in the browser can only mean the
    Next proxy couldn't reach this server."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"neuroSim hit an internal error ({type(err).__name__}). The API log has the traceback."},
    )


def _gemini(fn, *args):
    """Run a Gemini-backed call off the event loop; its refusals become 503s
    and bad input becomes 400s, both with a message the UI can show."""
    try:
        return fn(*args)
    except GeminiUnavailable as err:
        raise HTTPException(503, str(err)) from err
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


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
        return mocks.mock_genes()
    raise NotImplementedError  # bio.evidence.list_genes(disease)


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
        return mocks.mock_run(run_id)
    raise NotImplementedError  # pipeline.get_result(run_id)


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
        return mocks.mock_comparison(run_a, run_b)
    raise NotImplementedError  # pipeline.compare(run_a, run_b, level)


class ChatRequest(BaseModel):
    message: str
    interaction_id: str | None = None
    context: dict | None = None          # {"active_run": {"run_id", "human_gene", "mode", ...}}


@app.post("/agent/chat")
async def agent_chat(body: ChatRequest) -> dict:
    """{"message", "interaction_id": str | None, "context": {...} | None} in,
    {"reply", "tool_calls": [{"name", "arguments", "error"}], "run_ids",
    "interaction_id", "model"} out.
    The frontend keeps only the latest interaction_id (Gemini holds the history)
    and shows tool_calls so users see the agent used real results."""
    return await run_in_threadpool(_gemini, agent.chat, body.message, body.interaction_id, body.context)


@app.post("/runs/{run_id}/summary")
async def run_summary(run_id: str) -> dict:
    """Gemini's structured summary card for one run (cached per run): headline,
    top circuits with the run's own z-scores, caveats, one next experiment."""
    if USE_MOCKS:
        result = mocks.mock_run(run_id)
    else:
        raise NotImplementedError  # pipeline.get_result(run_id)
    return await run_in_threadpool(_gemini, summary.summarize_run, result)


@app.post("/evidence/extract")
async def evidence_extract(file: UploadFile) -> dict:
    """Upload a paper PDF; Gemini proposes evidence rows, each pending Bio's
    approval. Nothing is used until approved."""
    pdf = await file.read()
    return await run_in_threadpool(_gemini, papers.extract, pdf, file.filename or "paper.pdf")


class Decision(BaseModel):
    approve: bool


@app.post("/evidence/rows/{row_id}/decision")
def evidence_decision(row_id: str, body: Decision) -> dict:
    """Bio approves or rejects one proposed row. Approved rows go to
    data/evidence_approved.json, not evidence.json."""
    try:
        return papers.decide(row_id, body.approve)
    except KeyError as err:
        raise HTTPException(404, str(err.args[0])) from err
