"""Evidence extraction from papers (CS2 builds it, Bio approves every row).

Someone uploads a paper PDF, pastes its text, or gives its DOI or PMID. We
turn it into plain text with page markers, the model reads that and proposes
rows in the evidence.json schema, each with a verbatim supporting quote. Then
every row is checked against the evidence table (is the gene's ortholog
known, do the clusters map to connectome cell types, is the quote really in
the paper, is it a duplicate) and gets the confidence its seeds would get.

Nothing is used until Bio approves the row, optionally after editing it.
Approved rows are appended to config.APPROVED_EVIDENCE_PATH
(bio/evidence.load_evidence merges that file with data/evidence.json), never
written into evidence.json itself, and stay verified_by_bio=false until
someone checks the figures. The model never adds evidence on its own.

Proposals are kept in config.PROPOSALS_PATH so an API reload doesn't lose a
review in progress.

The model only ever sees text (ask_model below), so any model that can
return JSON can do the reading.
"""

from __future__ import annotations

import io
import json
import logging
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone

import httpx

from neurosim import config
from neurosim.agent import gemini
from neurosim.bio import evidence

ROW_FIELDS = ["disease", "human_gene", "fly_gene", "model_type", "clusters", "finding", "tier", "tier_reason", "quote", "page"]
EDITABLE = {"human_gene", "fly_gene", "model_type", "clusters", "finding", "tier"}
MODEL_TYPES = ["mutant", "RNAi", "overexpression", "other"]

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
                    "model_type": {"type": "string", "enum": MODEL_TYPES},
                    "clusters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Dopamine neuron clusters reported lost, e.g. PPL1, PPL2, PPM1/2, PPM3, PAL, PAM.",
                    },
                    "finding": {"type": "string", "description": "One plain sentence a judge can read: in this model, these neurons were lost."},
                    "tier": {"type": "string", "enum": ["high", "medium", "low"]},
                    "tier_reason": {"type": "string", "description": "Why this tier: counted per cluster with stats = high; reported loss without per-cluster counts = medium; indirect or conflicting = low."},
                    "quote": {"type": "string", "description": "One sentence copied word for word from the text that supports the row."},
                    "page": {"type": "integer", "description": "The [page N] marker the quote appears under; 0 if the text has no page markers."},
                },
                "required": ROW_FIELDS,
            },
        },
    },
    "required": ["citation", "url", "rows"],
}

INSTRUCTION = """\
You extract evidence rows for neuroSim from one fly (Drosophila) paper. A row
is one finding that, in a fly disease model, specific dopamine neurons were
lost or degenerated: which gene, which model, which neuron clusters. Only
include findings the paper itself reports with data (not ones it cites from
other work). If the paper has no such finding, return no rows. Quotes must be
copied word for word from the text. Do not guess clusters the paper doesn't
name; if it reports loss without naming clusters, say so in the finding,
leave clusters empty and use tier low. Name clusters as PPL1, PPL2, PPM1/2, PPM3, PAL or PAM (older
papers call PPL1 "DL1" and PPL2 "DL2"). Answer with JSON only, matching this
schema:
"""

# Cluster names as papers write them -> the evidence table's names.
# DL1/DL2 are the older names (Nässel and Elekes 1992) still used in some PD papers.
CLUSTER_ALIASES = {"DL1": "PPL1", "DL2": "PPL2", "PPM1": "PPM1/2", "PPM2": "PPM1/2", "PPM12": "PPM1/2", "PPL2AB": "PPL2", "PPL2C": "PPL2",
                   "ALL": "ALL_DA", "ALLDA": "ALL_DA", "TOTAL": "ALL_DA", "ALLDOPAMINERGIC": "ALL_DA"}


# --- Getting text ---------------------------------------------------------------


# Some journals (PNAS among them) set symbols in a Mathematical Pi font that
# pypdf reads as glyph names like "/H11001". The common ones, so "TH/H11001",
# "PPM1/H208622" and "10.1073/H20862pnas" read as TH+, PPM1/2 and a DOI.
GLYPHS = {"H20862": "/", "H20841": " · ", "H11001": "+", "H11545": "+", "H11002": "−", "H11003": "×", "H11005": "=",
          "H11006": "±", "H11021": "<", "H11022": ">", "H11015": "~", "H11011": "~", "H11032": "′", "H11033": "″",
          "H9004": "Δ", "H9251": "α", "H9252": "β", "H9253": "γ", "H9254": "δ", "H9262": "μ"}
_GLYPH_RE = re.compile("/(" + "|".join(sorted(GLYPHS, key=len, reverse=True)) + ")")


def clean_glyphs(text: str) -> str:
    return _GLYPH_RE.sub(lambda m: GLYPHS[m.group(1)], text)


def pdf_pages(pdf: bytes) -> list[str]:
    """The PDF's text, one string per page."""
    if len(pdf) > config.PAPER_MAX_BYTES:
        raise ValueError(f"The PDF is over {config.PAPER_MAX_BYTES // (1024 * 1024)} MB.")
    if not pdf.startswith(b"%PDF"):
        raise ValueError("That file isn't a PDF.")
    # pypdf warns about every font it can't fully parse; the text is still fine.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        from pypdf import PdfReader
    except ImportError as err:  # requirements.txt has it; an old venv may not
        raise ValueError("Reading PDFs needs pypdf: run pip install -r requirements.txt") from err
    try:
        pages = [clean_glyphs(page.extract_text() or "") for page in PdfReader(io.BytesIO(pdf)).pages]
    except Exception as err:  # pypdf raises many kinds on broken files
        raise ValueError(f"Couldn't read that PDF ({type(err).__name__}). Paste its text instead.") from err
    if sum(len(p.strip()) for p in pages) < 500:
        raise ValueError("That PDF has almost no text (a scan?). Paste the text or give the DOI instead.")
    return pages


DOI_RE = re.compile(r"10\.\d{4,9}/\S+")


def europe_pmc(identifier: str, full_text: bool = True) -> dict:
    """{"pages", "citation", "url", "read"} for a DOI or PMID from Europe PMC.
    pages is the full text when it is open access there ("read": "full text"),
    else title and abstract ("read": "abstract"). full_text=False only looks
    up the citation."""
    ident = identifier.strip().removeprefix("https://doi.org/").removeprefix("doi:").strip().rstrip(".,;)")
    if DOI_RE.fullmatch(ident):
        query = f'DOI:"{ident}"'
    elif ident.isdigit():
        query = f"EXT_ID:{ident} AND SRC:MED"
    else:
        raise ValueError("That doesn't look like a DOI (10.xxxx/...) or a PubMed ID.")
    base = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    try:
        with httpx.Client(timeout=20) as http:
            hits = http.get(f"{base}/search", params={"query": query, "resultType": "core", "format": "json"}).json()
            result = (hits.get("resultList", {}).get("result") or [None])[0]
            if result is None:
                raise ValueError(f"Europe PMC has no paper for {ident}.")
            full = ""
            pmcid = result.get("pmcid")
            if full_text and pmcid and result.get("isOpenAccess") == "Y":
                xml = http.get(f"{base}/{pmcid}/fullTextXML")
                if xml.status_code == 200:
                    full = _xml_text(xml.text)
    except (httpx.HTTPError, json.JSONDecodeError) as err:
        raise ValueError(f"Couldn't reach Europe PMC ({type(err).__name__}). Upload the PDF or paste the text instead.") from err
    authors = result.get("authorString", "")
    first = authors.split(",")[0].split(" ")[0] if authors else "Unknown"
    journal = result.get("journalTitle") or result.get("journalInfo", {}).get("journal", {}).get("title", "")
    citation = f"{first} et al. {result.get('pubYear', '')}, {journal}".strip(", ")
    url = f"https://doi.org/{result['doi']}" if result.get("doi") else f"https://europepmc.org/article/MED/{result.get('pmid', ident)}"
    text = full or f"{result.get('title', '')}\n\n{_xml_text(result.get('abstractText', ''))}"
    return {"pages": [text], "citation": citation, "url": url, "read": "full text" if full else "abstract"}


def _metadata(pages: list[str]) -> dict | None:
    """Europe PMC's record for the DOI printed near the start of a paper, or
    None when there is none or Europe PMC can't be reached."""
    doi = DOI_RE.search(" ".join(pages[:2]))
    if doi is None:
        return None
    try:
        return europe_pmc(doi.group(0), full_text=False)
    except ValueError:
        return None


def _xml_text(xml: str) -> str:
    text = re.sub(r"<(title|p|sec|caption)[^>]*>", "\n", xml)
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def _paper_text(pages: list[str]) -> str:
    """Pages joined with [page N] markers (none for a single unpaged text),
    without the reference list, cut to config.PAPER_MAX_CHARS."""
    text = pages[0] if len(pages) == 1 else "\n\n".join(f"[page {i}]\n{p}" for i, p in enumerate(pages, 1))
    # The reference list is long and full of other papers' findings.
    refs = [m.start() for m in re.finditer(r"\n\s*(References|REFERENCES|Literature Cited)\s*\n", text)]
    if refs and refs[-1] > len(text) * 0.5:
        text = text[:refs[-1]]
    return text[:config.PAPER_MAX_CHARS]


# --- Asking the model --------------------------------------------------------------


def ask_model(paper: str) -> tuple[dict, str]:
    """(answer in SCHEMA's shape, model name) for one paper's text."""
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
            input=[{"type": "text", "text": f"Extract the evidence rows from this paper.\n\n{paper}"}],
            system_instruction=INSTRUCTION + json.dumps(SCHEMA),
            response_format={"type": "text", "mime_type": "application/json", "schema": SCHEMA},
            generation_config={"thinking_level": "medium", "max_output_tokens": 12000},
            store=False,
            timeout=min(config.PAPER_TIMEOUT_S, left),
        )

    interaction = gemini.call(create, state)
    return parse_json(interaction.output_text or ""), state["model"]


def parse_json(text: str) -> dict:
    """The JSON object in a model's answer, tolerating a ```json fence or prose around it."""
    start, end = text.find("{"), text.rfind("}")
    try:
        raw = json.loads(text[start:end + 1] if start >= 0 else text)
    except json.JSONDecodeError as err:
        raise gemini.GeminiUnavailable(f"The model returned rows that aren't valid JSON: {err}") from err
    if not isinstance(raw, dict):
        raise gemini.GeminiUnavailable("The model returned JSON that isn't an object.")
    return raw


# --- Checking rows -----------------------------------------------------------------


def _squash(text: str) -> str:
    """Letters and digits only, lowercased, ligatures and line-break hyphens
    undone: how a quote is matched against PDF text."""
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"-\s*\n\s*", "", text)
    return re.sub(r"[^0-9a-z]", "", text.lower())


def find_quote(quote: str, pages: list[str]) -> tuple[bool | None, int | None]:
    """(found word for word, page it is on). Page is None for unpaged text."""
    q = _squash(quote)
    if len(q) < 20:
        return None, None
    paged = len(pages) > 1
    for i, page in enumerate(pages, 1):
        if q in _squash(page):
            return True, i if paged else None
    if paged:  # a quote that runs over a page break
        for i in range(1, len(pages)):
            if q in _squash(pages[i - 1][-2000:] + pages[i][:2000]):
                return True, i
    return False, None


def normalize_clusters(clusters: list[str]) -> list[str]:
    known = {k for k in evidence.load_evidence().get("cluster_to_cell_types", {}) if not k.startswith("_")}
    by_key = {re.sub(r"[^0-9A-Z]", "", k.upper()): k for k in known}
    out = []
    for name in clusters:
        key = re.sub(r"\b(CLUSTERS?|NEURONS?|DANS?|DA)\b", "", name.upper())
        key = re.sub(r"[^0-9A-Z]", "", key)
        fixed = by_key.get(key) or CLUSTER_ALIASES.get(key) or name.strip()
        if fixed not in out:
            out.append(fixed)
    return out


def _citation_key(citation: str) -> str:
    """'Wang et al. 2006, PNAS' -> 'wang2006'."""
    author = re.match(r"\s*([^\W\d_]+)", citation or "")
    year = re.search(r"(19|20)\d\d", citation or "")
    return (author.group(1).lower() if author else "") + (year.group(0) if year else "")


def check_row(row: dict) -> dict:
    """What will happen to this row in a simulation, in plain terms."""
    table = evidence.load_evidence()
    problems: list[str] = []
    entry = table["orthologs"].get(row["human_gene"])
    if entry is None:
        ortholog = {"known": False, "fly_genes": [], "fly_gene_matches": False, "confidence": 0.0}
        problems.append(f"{row['human_gene']} isn't in the ortholog table, so this row can't seed a run until Bio adds it.")
    else:
        orth = evidence.find_ortholog(row["human_gene"])
        matches = row["fly_gene"].lower() in {g.lower() for g in orth.fly_genes}
        ortholog = {"known": True, "fly_genes": orth.fly_genes, "fly_gene_matches": matches, "confidence": orth.confidence}
        if not orth.fly_genes:
            problems.append(f"{row['human_gene']} has no fly ortholog in the table, so it can't be simulated.")
        elif not matches:
            problems.append(f"The table's fly ortholog of {row['human_gene']} is {', '.join(orth.fly_genes)}, not {row['fly_gene']}.")

    clusters = []
    for name in row["clusters"]:
        match, cell_types = evidence.cluster_cell_types(name)
        known = name in table.get("cluster_to_cell_types", {})
        clusters.append({"name": name, "known": known, "match": match if known else None, "n_cell_types": len(cell_types)})
        if not known:
            problems.append(f"Cluster {name} isn't in the cluster table, so it seeds no neurons.")
    if not row["clusters"]:
        problems.append("No clusters named, so this row seeds no neurons.")

    seedable = [c for c in clusters if c["known"]]
    confidence = None
    if ortholog["fly_genes"] and seedable:
        best = max(config.TYPE_MATCH_WEIGHT[c["match"]] for c in seedable)
        confidence = round(ortholog["confidence"] * config.EVIDENCE_TIER_WEIGHT[row["tier"]] * best, 3)

    key = _citation_key(row["citation"])
    duplicate = any(
        r.human_gene == row["human_gene"] and set(r.clusters) == set(row["clusters"])
        and key and _citation_key(r.citation) == key
        for r in table["evidence"]
    )
    if duplicate:
        problems.append("The evidence table already has this gene, clusters and paper.")
    if row.get("extracted_by") == config.AGENT_FALLBACK_MODEL:
        problems.append(f"Read by the backup model ({config.AGENT_FALLBACK_MODEL}) because the main one was busy. "
                        "Check it more closely, or try the paper again in a minute.")
    if row.get("read") == "abstract" and not row["clusters"]:
        problems.append("Only the abstract was read. Upload the PDF to find which clusters were lost.")
    if row.get("quote_found") is False:
        problems.append("The quote isn't in the paper's text word for word. Check it before approving.")
    return {"ortholog": ortholog, "clusters": clusters, "confidence": confidence, "can_seed": confidence is not None,
            "duplicate": duplicate, "problems": problems}


# --- Proposals ------------------------------------------------------------------------


_PROPOSALS: dict[str, dict] | None = None   # row id -> row


def _proposals() -> dict[str, dict]:
    global _PROPOSALS
    if _PROPOSALS is None:
        path = config.PROPOSALS_PATH
        _PROPOSALS = {r["id"]: r for r in json.loads(path.read_text())} if path.exists() else {}
    return _PROPOSALS


def _save_proposals() -> None:
    config.PROPOSALS_PATH.write_text(json.dumps(list(_proposals().values()), indent=1) + "\n")


def extract(pdf: bytes | None = None, filename: str = "paper.pdf", text: str | None = None, doi: str | None = None) -> dict:
    """Propose rows from exactly one of: a PDF, pasted text, or a DOI/PMID."""
    if sum(x is not None and x != "" for x in (pdf, text, doi)) != 1:
        raise ValueError("Give one of: a PDF, the paper's text, or its DOI.")
    if pdf:
        pages, source, read = pdf_pages(pdf), filename, "PDF"
        meta = _metadata(pages)
    elif text:
        if len(text.strip()) < 200:
            raise ValueError("That text is too short to hold a finding. Paste at least the abstract.")
        pages, source, read = [text], "pasted text", "pasted text"
        meta = _metadata(pages)
    else:
        meta = europe_pmc(doi)
        pages, source, read = meta["pages"], doi.strip(), meta["read"]

    raw, model = ask_model(_paper_text(pages))
    # The published record beats the model's reading of the title page.
    citation = meta["citation"] if meta else raw.get("citation", "")
    url = meta["url"] if meta else raw.get("url", "")

    rows = []
    for r in raw.get("rows", []):
        if not isinstance(r, dict):
            continue
        found, page = find_quote(r.get("quote", ""), pages)
        row = {
            "id": uuid.uuid4().hex[:12],
            "status": "pending",
            **{k: r.get(k) for k in ROW_FIELDS},
            "human_gene": str(r.get("human_gene") or "").strip().upper(),
            "fly_gene": str(r.get("fly_gene") or "").strip(),
            "model_type": r.get("model_type") if r.get("model_type") in MODEL_TYPES else "other",
            "clusters": normalize_clusters([str(c) for c in r.get("clusters") or []]),
            "tier": r.get("tier") if r.get("tier") in config.EVIDENCE_TIER_WEIGHT else "low",
            "disease": str(r.get("disease") or "parkinsons").strip().lower(),
            # The page we found the quote on beats the model's guess.
            "page": page if found else (r.get("page") or None),
            "quote_found": found,
            "citation": citation,
            "url": url,
            "source_file": source,
            "read": read,
            "extracted_by": model,
            "edited": [],
        }
        if not row["clusters"]:  # loss with no named clusters can't seed a simulation on its own
            row["tier"] = "low"
        row["checks"] = check_row(row)
        _proposals()[row["id"]] = row
        rows.append(row)
    _save_proposals()
    note = None
    if read == "abstract":
        note = "Only the abstract was available, and abstracts rarely name neuron clusters. Upload the PDF to get per-cluster findings."
    return {"citation": citation, "url": url, "file": source, "read": read, "note": note, "model": model,
            "fallback": model == config.AGENT_FALLBACK_MODEL, "rows": rows}


def pending() -> list[dict]:
    """Rows still waiting for Bio, oldest first, with fresh checks (the table may have changed)."""
    rows = [r for r in _proposals().values() if r["status"] == "pending"]
    for row in rows:
        row["checks"] = check_row(row)
    return rows


def _apply_edits(row: dict, edits: dict) -> None:
    unknown = set(edits) - EDITABLE
    if unknown:
        raise ValueError(f"These fields can't be edited: {', '.join(sorted(unknown))}.")
    if "tier" in edits and edits["tier"] not in config.EVIDENCE_TIER_WEIGHT:
        raise ValueError("Tier must be high, medium or low.")
    if "model_type" in edits and edits["model_type"] not in MODEL_TYPES:
        raise ValueError(f"Model type must be one of {', '.join(MODEL_TYPES)}.")
    if "clusters" in edits:
        if not isinstance(edits["clusters"], list):
            raise ValueError("Clusters must be a list of names.")
        edits = {**edits, "clusters": normalize_clusters([str(c) for c in edits["clusters"] if str(c).strip()])}
    if "human_gene" in edits:
        edits = {**edits, "human_gene": str(edits["human_gene"]).strip().upper()}
    for key, value in edits.items():
        if isinstance(value, str):
            value = value.strip()
        if value != row[key]:
            row[key] = value
            if key not in row["edited"]:
                row["edited"].append(key)
    if not row["human_gene"] or not row["finding"]:
        raise ValueError("A row needs a human gene and a finding.")


def decide(row_id: str, approve: bool, edits: dict | None = None) -> dict:
    """Bio's decision on one proposed row, with any corrections. Approving
    appends it to the approved-evidence file in the evidence.json row shape."""
    row = _proposals().get(row_id)
    if row is None:
        raise KeyError(f"No proposed row {row_id}.")
    if row["status"] != "pending":
        return row
    if edits:
        _apply_edits(row, edits)
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
            "citation": row["citation"] or row["source_file"],
            "url": row["url"],
            "tier": row["tier"],
            "verified_by_bio": False,
            "extracted": {
                "id": row["id"],
                "by": row["extracted_by"],
                "file": row["source_file"],
                "quote": row["quote"],
                "page": row["page"],
                "quote_found": row["quote_found"],
                "tier_reason": row["tier_reason"],
                "edited": row["edited"],
                "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        })
        path.write_text(json.dumps(approved, indent=2) + "\n")
    row["checks"] = check_row(row)
    _save_proposals()
    return row


def approved_rows() -> list[dict]:
    path = config.APPROVED_EVIDENCE_PATH
    return json.loads(path.read_text())["evidence"] if path.exists() else []


def remove_approved(row_id: str) -> None:
    """Take an approved row back out of the evidence table."""
    path = config.APPROVED_EVIDENCE_PATH
    rows = approved_rows()
    kept = [r for r in rows if r.get("extracted", {}).get("id") != row_id]
    if len(kept) == len(rows):
        raise KeyError(f"No approved row {row_id}.")
    path.write_text(json.dumps({"evidence": kept}, indent=2) + "\n")
    if row_id in _proposals():
        _proposals()[row_id]["status"] = "removed"
        _save_proposals()
