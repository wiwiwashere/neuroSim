"""Lightweight Vercel API for the repository's committed sample-data mode.

The full local API imports the scientific engine and its large optional data
stack. Vercel does not have the uncommitted FlyWire dataset, so importing that
stack only bloats the serverless bundle. This module exposes the same core API
contract with the existing sample payloads and disables stateful/LLM features
that require durable storage or a secret.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from neurosim import config
from neurosim.api import mocks
from neurosim.bio import evidence, expression, targets
from neurosim.models import GroupLevel, SimulationRequest


config.USE_MOCKS = True
app = FastAPI(title="neuroSim", description="Vercel sample-data deployment", root_path="/api")


@app.exception_handler(Exception)
async def _unhandled(_request, err: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": f"neuroSim hit an internal error ({type(err).__name__})."},
    )


@app.get("/diseases")
def diseases() -> list[str]:
    return evidence.list_diseases()


@app.get("/diseases/{disease}/genes")
def genes(disease: str) -> list[dict]:
    return evidence.list_genes(disease)


@app.get("/genes/{human_gene}/chain")
def mapping_chain(human_gene: str, high_confidence_only: bool = False, disease: str | None = None) -> dict:
    request = SimulationRequest(
        human_gene=human_gene,
        high_confidence_only=high_confidence_only,
        disease=disease,
    )
    return mocks.mock_seeds(request).model_dump()


@app.get("/genes/{human_gene}/expression")
def gene_expression(human_gene: str):
    return expression.gene_expression(human_gene)


@app.get("/genes/{human_gene}/targets")
def direct_targets(human_gene: str, high_confidence_only: bool = False, disease: str | None = None):
    return targets.direct_targets(human_gene, high_confidence_only, disease=disease)


@app.post("/simulate")
def simulate(request: SimulationRequest):
    return mocks.mock_result(request)


@app.get("/runs/{run_id}")
def run(run_id: str):
    return mocks.mock_run(run_id)


@app.get("/runs/{run_id}/sankey")
def sankey(run_id: str):
    del run_id
    return mocks.mock_sankey()


@app.get("/runs/{run_id}/subgraph")
def subgraph(run_id: str):
    del run_id
    return mocks.mock_subgraph()


@app.get("/runs/{run_id}/dynamics")
def dynamics(run_id: str, n_regions: int = 10, T: float = 10.0):
    return mocks.mock_dynamics(run_id, n_regions, T)


@app.get("/runs/{run_id}/neurons/{root_id}/explain")
def explain(run_id: str, root_id: int) -> dict:
    del run_id
    return {
        "root_id": str(root_id),
        "paths": [{"neurons": ["PPL101", "MBON01"], "strength": 0.41}],
    }


@app.get("/compare")
def compare(run_a: str, run_b: str, level: GroupLevel = GroupLevel.REGION):
    del level
    return mocks.mock_comparison(run_a, run_b)


@app.get("/agent/llm")
def agent_llm() -> dict:
    return {
        "family": config.LLM,
        "name": config.LLM_NAME,
        "model": config.AGENT_MODEL,
        "fallback_model": config.AGENT_FALLBACK_MODEL,
    }


def _unavailable() -> None:
    raise HTTPException(
        status_code=503,
        detail="This public demo does not have a Gemini API key or durable writable storage.",
    )


@app.post("/agent/chat")
@app.post("/runs/{_run_id}/summary")
@app.post("/evidence/extract")
@app.post("/evidence/rows/{_row_id}/decision")
@app.delete("/evidence/approved/{_row_id}")
@app.post("/custom/preview")
@app.post("/custom/diseases")
@app.delete("/custom/diseases/{_disease_id}")
def unavailable_feature(_run_id: str | None = None, _row_id: str | None = None, _disease_id: str | None = None):
    _unavailable()


@app.get("/evidence/proposals")
@app.get("/evidence/approved")
@app.get("/custom/diseases")
def empty_collection() -> list:
    return []


@app.get("/custom/names")
def custom_names(q: str = "") -> list:
    del q
    return []


@app.get("/custom/template.json")
def custom_template() -> dict:
    return {"rows": [], "note": "Custom diseases are disabled in the public demo."}
