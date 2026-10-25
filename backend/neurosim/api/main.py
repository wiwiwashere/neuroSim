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

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from neurosim import config
from neurosim.agent import agent, papers, summary
from neurosim.agent.gemini import GeminiUnavailable
from neurosim.api import mocks
from neurosim.bio import evidence, expression
from neurosim.engine import degeneration, pipeline
from neurosim.engine.graph import processed_data_available, set_connectome
from neurosim.models import (
    Comparison,
    DegenerationSeries,
    GeneExpression,
    GroupLevel,
    SankeyLink,
    SimulationRequest,
    SimulationResult,
    Subgraph,
)

USE_SYNTHETIC = os.environ.get("NEUROSIM_SYNTHETIC") == "1"
_MOCKS_ENV = os.environ.get("NEUROSIM_MOCKS")
if USE_SYNTHETIC:
    USE_MOCKS = False
elif _MOCKS_ENV is not None:
    USE_MOCKS = _MOCKS_ENV == "1"
else:
    USE_MOCKS = not (processed_data_available() and pipeline.engine_ready())
# The agent's tools read config.USE_MOCKS, so they serve what the API serves.
config.USE_MOCKS = USE_MOCKS

if USE_SYNTHETIC:
    from neurosim.engine.synthetic import synthetic_connectome

    set_connectome(synthetic_connectome())

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
    return evidence.list_diseases()


@app.get("/diseases/{disease}/genes")
def genes(disease: str) -> list[dict]:
    """Gene picker: gene, fly ortholog, confidence, whether it can be simulated.
    Always from the evidence table (it needs no engine), so a gene that only
    an approved paper row mentions shows up too."""
    return evidence.list_genes(disease)


@app.get("/genes/{human_gene}/chain")
def mapping_chain(human_gene: str, high_confidence_only: bool = False) -> dict:
    """Everything for the mapping-chain screen: ortholog, evidence rows,
    clusters, cell types, neuron counts, confidence at every link."""
    request = SimulationRequest(human_gene=human_gene, high_confidence_only=high_confidence_only)
    with _http_errors():
        return (mocks.mock_seeds(request) if USE_MOCKS else evidence.resolve_seeds(request)).model_dump()


@app.get("/genes/{human_gene}/expression")
def gene_expression(human_gene: str) -> GeneExpression | None:
    """Kait's atlas values for the gene's fly orthologs (PAM only), or null.
    From the evidence table, so it works for genes that can't be simulated yet."""
    return expression.gene_expression(human_gene)


@app.post("/simulate")
def simulate(request: SimulationRequest) -> SimulationResult:
    """Run (or fetch from cache) one experiment."""
    with _http_errors():
        return mocks.mock_result(request) if USE_MOCKS else pipeline.run_simulation(request)


@app.get("/runs/{run_id}")
def run(run_id: str) -> SimulationResult:
    if USE_MOCKS:
        return mocks.mock_run(run_id)
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


@app.get("/runs/{run_id}/dynamics")
async def dynamics(run_id: str, n_regions: int = 10, T: float = 10.0) -> DegenerationSeries:
    """neurolib / Wilson–Cowan time-series: how activity in the top affected
    regions evolves as seed neurons lose function over simulated time T.
    CPU-bound; runs off the event loop."""
    if USE_MOCKS:
        return mocks.mock_dynamics(run_id, n_regions, T)
    with _http_errors():
        return await run_in_threadpool(degeneration.run_dynamics, run_id, n_regions, T)


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
    with _http_errors():
        return pipeline.compare(run_a, run_b, level)


class ChatRequest(BaseModel):
    message: str
    interaction_id: str | None = None
    context: dict | None = None          # {"active_run": {"run_id", "human_gene", "mode", ...}}


@app.get("/agent/llm")
def agent_llm() -> dict:
    """Which model family answers the agent, summaries and paper extraction
    (NEUROSIM_LLM), so the UI can name it."""
    return {"family": config.LLM, "name": config.LLM_NAME, "model": config.AGENT_MODEL,
            "fallback_model": config.AGENT_FALLBACK_MODEL}


@app.post("/agent/chat")
async def agent_chat(body: ChatRequest) -> dict:
    """{"message", "interaction_id": str | None, "context": {...} | None} in,
    {"reply", "tool_calls": [{"name", "arguments", "error"}], "run_ids",
    "interaction_id", "model"} out.
    The frontend keeps only the latest interaction_id (Gemini's server or, for
    Gemma, agent.py holds the history)
    and shows tool_calls so users see the agent used real results."""
    return await run_in_threadpool(_gemini, agent.chat, body.message, body.interaction_id, body.context)


@app.post("/runs/{run_id}/summary")
async def run_summary(run_id: str) -> dict:
    """The model's structured summary card for one run (cached per run): headline,
    top circuits with the run's own z-scores, caveats, one next experiment."""
    if USE_MOCKS:
        result = mocks.mock_run(run_id)
    else:
        with _http_errors():
            result = pipeline.get_result(run_id)
    return await run_in_threadpool(_gemini, summary.summarize_run, result)


@app.post("/evidence/extract")
async def evidence_extract(
    file: UploadFile | None = None, text: str | None = Form(None), doi: str | None = Form(None)
) -> dict:
    """Send one of: a paper PDF (file), its text (text), or a DOI/PMID (doi).
    The model proposes evidence rows, each checked against the evidence table
    and pending Bio's approval. Nothing is used until approved."""
    pdf = await file.read() if file is not None else None
    name = file.filename if file is not None and file.filename else "paper.pdf"
    return await run_in_threadpool(lambda: _gemini(lambda: papers.extract(pdf, name, text, doi)))


@app.get("/evidence/proposals")
def evidence_proposals() -> list[dict]:
    """Rows from earlier uploads still waiting for a decision."""
    return papers.pending()


class Decision(BaseModel):
    approve: bool
    edits: dict | None = None    # any of human_gene, fly_gene, model_type, clusters, finding, tier


@app.post("/evidence/rows/{row_id}/decision")
def evidence_decision(row_id: str, body: Decision) -> dict:
    """Bio approves (optionally with corrections) or rejects one proposed row.
    Approved rows go to data/evidence_approved.json, not evidence.json, and
    seed the next run."""
    try:
        row = papers.decide(row_id, body.approve, body.edits)
    except KeyError as err:
        raise HTTPException(404, str(err.args[0])) from err
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    if row["status"] == "approved":
        pipeline.clear_cache()   # cached runs were seeded without this row
    return row


@app.get("/evidence/approved")
def evidence_approved() -> list[dict]:
    """Rows approved from paper uploads, newest last."""
    return papers.approved_rows()


@app.delete("/evidence/approved/{row_id}")
def evidence_remove(row_id: str) -> dict:
    """Take an approved paper row back out of the evidence table."""
    try:
        papers.remove_approved(row_id)
    except KeyError as err:
        raise HTTPException(404, str(err.args[0])) from err
    pipeline.clear_cache()
    return {"removed": row_id}
