"""Evidence extraction from papers (CS2 builds it, Bio approves every row).

Someone uploads a paper PDF. Gemini reads it and proposes rows in the
evidence.json schema, each with a verbatim supporting quote and its page.
Nothing is used until Bio approves the row; approved rows are appended to
config.APPROVED_EVIDENCE_PATH (bio/evidence.load_evidence merges that file
with data/evidence.json), never written into evidence.json itself, and stay
verified_by_bio=false until someone checks the figures. Gemini never adds
evidence on its own.

Proposals live in memory: restarting the API drops the ones not yet decided.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import datetime, timezone

from neurosim import config
from neurosim.agent import gemini

SCHEMA = {
    "type": "object",
    "properties": {
        "citation": {"type": "string", "description": "First author et al. year, journal. e.g. 'Wang et al. 2006, PNAS'."},
        "url": {"type": "string", "description": "The paper's DOI or URL if printed in it, else empty."},
        "rows": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "disease": {"type": "string", "description": "Lowercase id, e.g. 'parkinsons', 'als'."},
                    "human_gene": {"type": "string", "description": "Human gene symbol, e.g. PINK1. 'none' if the model expresses a human protein."},
                    "fly_gene": {"type": "string", "description": "Drosophila gene symbol as written, e.g. Pink1, park."},
                    "model_type": {"type": "string", "enum": ["mutant", "RNAi", "overexpression", "other"]},
                    "clusters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Neuron clusters reported lost, in the paper's names (PPL1, PPM1/2, PPM3, PAL, PAM, ...).",
                    },
                    "finding": {"type": "string", "description": "One plain sentence a judge can read: in this model, these neurons were lost."},
                    "tier": {"type": "string", "enum": ["high", "medium", "low"]},
                    "tier_reason": {"type": "string", "description": "Why this tier: counted per cluster with stats = high; reported loss without per-cluster counts = medium; indirect or conflicting = low."},
                    "quote": {"type": "string", "description": "Verbatim sentence from the paper that supports the row."},
                    "page": {"type": "integer", "description": "PDF page number of the quote, starting at 1."},
                },
                "required": ["disease", "human_gene", "fly_gene", "model_type", "clusters", "finding", "tier", "tier_reason", "quote", "page"],
            },
        },
    },
    "required": ["citation", "url", "rows"],
}

INSTRUCTION = """\
You extract evidence rows for neuroSim from one fly (Drosophila) paper. A row
is one finding that, in a fly disease model, specific neurons were lost or
degenerated: which gene, which model, which neuron clusters. Only include
findings the paper itself reports with data (not ones it cites from other
work). If the paper has no such finding, return no rows. Quotes must be
copied word for word from the paper. Do not guess clusters the paper doesn't
name; if it reports loss without naming clusters, say so in the finding and
use tier low.
"""

_PROPOSALS: dict[str, dict] = {}   # row id -> row


def extract(pdf: bytes, filename: str) -> dict:
    if len(pdf) > config.PAPER_MAX_BYTES:
        raise ValueError(f"The PDF is over {config.PAPER_MAX_BYTES // (1024 * 1024)} MB.")
    if not pdf.startswith(b"%PDF"):
        raise ValueError("That file isn't a PDF.")
    state: dict = {}
    deadline = time.monotonic() + config.PAPER_DEADLINE_S

    def create(model: str):
        left = deadline - time.monotonic()
        if left <= 0:
            raise gemini.GeminiUnavailable(
                f"Gemini couldn't read the paper within {config.PAPER_DEADLINE_S / 60:g} minutes. Try again in a minute."
            )
        return gemini.client().interactions.create(
            model=model,
            input=[
                {"type": "document", "mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()},
                {"type": "text", "text": "Extract the evidence rows from this paper."},
            ],
            system_instruction=INSTRUCTION,
            response_format={"type": "text", "mime_type": "application/json", "schema": SCHEMA},
            generation_config={"thinking_level": "medium", "max_output_tokens": 12000},
            store=False,
            timeout=min(config.PAPER_TIMEOUT_S, left),
        )

    interaction = gemini.call(create, state)
    try:
        raw = json.loads(interaction.output_text or "")
    except json.JSONDecodeError as err:
        raise gemini.GeminiUnavailable(f"Gemini returned rows that aren't valid JSON: {err}") from err

    rows = []
    for r in raw.get("rows", []):
        row = {
            "id": uuid.uuid4().hex[:12],
            "status": "pending",
            **{k: r.get(k) for k in SCHEMA["properties"]["rows"]["items"]["properties"]},
            "human_gene": (r.get("human_gene") or "").upper(),
            # Loss with no named clusters can't seed a simulation on its own.
            **({"tier": "low"} if not r.get("clusters") else {}),
            "citation": raw.get("citation", ""),
            "url": raw.get("url", ""),
            "source_file": filename,
            "extracted_by": state["model"],
        }
        _PROPOSALS[row["id"]] = row
        rows.append(row)
    return {"citation": raw.get("citation", ""), "url": raw.get("url", ""), "file": filename, "model": state["model"], "rows": rows}


def decide(row_id: str, approve: bool) -> dict:
    """Bio's decision on one proposed row. Approving appends it to the
    approved-evidence file in the evidence.json row shape."""
    row = _PROPOSALS.get(row_id)
    if row is None:
        raise KeyError(f"No proposed row {row_id}; proposals are dropped when the API restarts.")
    if row["status"] != "pending":
        return row
    row["status"] = "approved" if approve else "rejected"
    if approve:
        path = config.APPROVED_EVIDENCE_PATH
        approved = json.loads(path.read_text()) if path.exists() else {"evidence": []}
        approved["evidence"].append({
            "disease": row["disease"],
            "human_gene": row["human_gene"],
            "fly_gene": row["fly_gene"],
            "model_type": row["model_type"],
            "clusters": row["clusters"],
            "finding": row["finding"],
            "citation": row["citation"],
            "url": row["url"],
            "tier": row["tier"],
            "verified_by_bio": False,
            "extracted": {
                "by": row["extracted_by"],
                "file": row["source_file"],
                "quote": row["quote"],
                "page": row["page"],
                "tier_reason": row["tier_reason"],
                "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        })
        path.write_text(json.dumps(approved, indent=2) + "\n")
    return row
