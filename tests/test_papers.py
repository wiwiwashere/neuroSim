"""Paper upload: text in, checked rows out, Bio's decisions into the evidence
table. The model is the fake client from test_agent, so these run offline."""

import json
from types import SimpleNamespace

import httpx
import pytest

from neurosim import config
from neurosim.agent import papers
from neurosim.bio import evidence
from neurosim.engine.graph import set_connectome
from neurosim.engine.synthetic import synthetic_connectome
from neurosim.models import SimulationRequest

from test_agent import StatusError, _interaction, fake  # noqa: F401  (fake is a fixture)

ABSTRACT = (
    "Mutations in PINK1 cause early-onset Parkinson's disease. Here we knocked down Pink1 in Drosophila "
    "dopaminergic neurons by RNAi. Aged Pink1 RNAi flies showed a significant loss of PPL1 cluster "
    "dopaminergic neurons compared with controls, while the PAM cluster was unaffected. "
    "Climbing ability declined in parallel with the neuron loss."
)
REAL_CLIENT = httpx.Client
QUOTE = "Aged Pink1 RNAi flies showed a significant loss of PPL1 cluster dopaminergic neurons compared with controls"


def _row(**over):
    row = {"disease": "parkinsons", "human_gene": "pink1", "fly_gene": "Pink1", "model_type": "RNAi",
           "clusters": ["PPL1 cluster"], "finding": "Pink1 RNAi flies lose PPL1 neurons.", "tier": "medium",
           "tier_reason": "Loss reported without per-cluster counts.", "quote": QUOTE, "page": 0}
    return {**row, **over}


def _answer(*rows, citation="Doe et al. 2020, Fly Journal"):
    return _interaction("p1", text=json.dumps({"citation": citation, "url": "", "rows": list(rows)}))


def test_rows_wait_for_approval_and_then_seed_the_next_run(fake):
    sent = fake([_answer(_row(), _row(clusters=["PAM"], quote="not in the text at all, made up by the model"))])
    out = papers.extract(text=ABSTRACT)

    assert ABSTRACT in sent.sent[0]["input"][0]["text"]
    assert not config.APPROVED_EVIDENCE_PATH.exists()        # nothing saved before a decision
    first, second = out["rows"]
    assert first["human_gene"] == "PINK1" and first["status"] == "pending"
    assert first["clusters"] == ["PPL1"]                       # "PPL1 cluster" -> the table's name
    assert first["quote_found"] is True and first["page"] is None
    checks = first["checks"]
    assert checks["ortholog"]["fly_gene_matches"] and checks["can_seed"] and not checks["problems"]
    orth = evidence.find_ortholog("PINK1").confidence
    assert checks["confidence"] == round(orth * config.EVIDENCE_TIER_WEIGHT["medium"] * 1.0, 3)
    assert second["quote_found"] is False and any("quote" in p for p in second["checks"]["problems"])

    papers.decide(first["id"], True, {"tier": "high"})
    papers.decide(second["id"], False)
    saved = json.loads(config.APPROVED_EVIDENCE_PATH.read_text())["evidence"]
    assert len(saved) == 1
    assert saved[0]["verified_by_bio"] is False and saved[0]["tier"] == "high"
    assert saved[0]["extracted"]["quote"] == QUOTE and saved[0]["extracted"]["edited"] == ["tier"]

    # The approved row is in the table, and PINK1 now also seeds PPL1.
    set_connectome(synthetic_connectome())
    try:
        seeds = evidence.resolve_seeds(SimulationRequest(human_gene="PINK1"))
    finally:
        set_connectome(None)
    ppl1 = [t for t in seeds.seed_types if t.cluster == "PPL1"]
    assert ppl1 and all(t.evidence[0].extracted.id == first["id"] for t in ppl1)


def test_pdf_quotes_are_found_on_their_page(fake, monkeypatch):
    pages = ["Title page. " * 50, "Results. " + ABSTRACT]
    monkeypatch.setattr(papers, "pdf_pages", lambda pdf: pages)
    sent = fake([_answer(_row(page=7))])
    out = papers.extract(b"%PDF-1.4 fake", "doe.pdf")

    assert "[page 2]" in sent.sent[0]["input"][0]["text"]
    assert out["rows"][0]["page"] == 2 and out["rows"][0]["quote_found"] is True
    assert out["file"] == "doe.pdf"


def test_real_pdf_text_is_read(fake):
    pytest.importorskip("pypdf")
    pdf = _tiny_pdf(["First page " * 60, ABSTRACT])
    assert "PPL1 cluster" in papers.pdf_pages(pdf)[1]


def test_problems_are_spelled_out(fake):
    fake([_answer(_row(human_gene="VPS35", fly_gene="Vps35", clusters=["PPM1", "PPM2", "DL1 neurons", "PPL9"]),
                  _row(fly_gene="park"), _row(clusters=[]))])
    new_gene, wrong_fly, no_clusters = papers.extract(text=ABSTRACT)["rows"]

    assert new_gene["clusters"] == ["PPM1/2", "PPL1", "PPL9"]
    problems = " ".join(new_gene["checks"]["problems"])
    assert "VPS35 isn't in the ortholog table" in problems and "Cluster PPL9" in problems
    assert new_gene["checks"]["can_seed"] is False
    assert "not park" in " ".join(wrong_fly["checks"]["problems"])
    assert no_clusters["tier"] == "low" and no_clusters["checks"]["can_seed"] is False

    # Approving a gene the ortholog table lacks lists it as not simulatable instead of breaking the picker.
    papers.decide(new_gene["id"], True)
    genes = {g["human_gene"]: g for g in evidence.list_genes("parkinsons")}
    assert genes["VPS35"]["simulatable"] is False


def test_paper_spellings_of_the_fly_gene_are_the_tables(fake):
    fake([_answer(_row(fly_gene="dPink1"), _row(fly_gene="dPINK1"), _row(fly_gene="PINK1"), _row(fly_gene="Parkin"))])
    rows = papers.extract(text=ABSTRACT)["rows"]
    assert [r["fly_gene"] for r in rows] == ["Pink1", "Pink1", "Pink1", "Parkin"]
    assert [r["checks"]["ortholog"]["fly_gene_matches"] for r in rows] == [True, True, True, False]


def test_clusters_the_quote_doesnt_name_are_flagged(fake):
    fake([_answer(_row(clusters=["PPL1", "PPM1/2"]), _row(clusters=["PPM1/2"], quote="TH+ neurons were lost in the PPM1 cluster of aged flies."))])
    unsupported, alias = papers.extract(text=ABSTRACT)["rows"]
    assert [c["in_quote"] for c in unsupported["checks"]["clusters"]] == [True, False]
    assert any("doesn't mention PPM1/2" in p for p in unsupported["checks"]["problems"])
    assert alias["checks"]["clusters"][0]["in_quote"] is True     # "PPM1" names PPM1/2


def test_duplicates_of_the_table_are_flagged(fake):
    fake([_answer(_row(human_gene="PRKN", fly_gene="park", clusters=["PPL1"]), citation="Whitworth et al. 2005, PNAS")])
    row = papers.extract(text=ABSTRACT)["rows"][0]
    assert row["checks"]["duplicate"] is True

    # Same paper and gene with other clusters (Wang 2006 read live: the table's four plus PPL1).
    fake([_answer(_row(clusters=["PAL", "PPM1/2", "PPM3", "PPL2", "PPL1"]), citation="Wang et al. 2006, PNAS")])
    row = papers.extract(text=ABSTRACT)["rows"][0]
    assert row["checks"]["duplicate"] is False
    assert any("already has PINK1 from this paper (PAL, PPM1/2, PPM3, PPL2)" in p for p in row["checks"]["problems"])


def test_proposals_survive_a_reload_and_approvals_can_be_removed(fake, monkeypatch):
    fake([_answer(_row())])
    row_id = papers.extract(text=ABSTRACT)["rows"][0]["id"]
    monkeypatch.setattr(papers, "_PROPOSALS", None)            # what an API reload does
    assert [r["id"] for r in papers.pending()] == [row_id]

    papers.decide(row_id, True)
    assert papers.pending() == [] and len(papers.approved_rows()) == 1
    papers.remove_approved(row_id)
    assert papers.approved_rows() == []
    assert not [r for r in evidence.evidence_for("PINK1") if r.extracted]
    with pytest.raises(KeyError):
        papers.remove_approved(row_id)


def test_bad_edits_are_refused(fake):
    fake([_answer(_row())])
    row_id = papers.extract(text=ABSTRACT)["rows"][0]["id"]
    with pytest.raises(ValueError, match="Tier"):
        papers.decide(row_id, True, {"tier": "certain"})
    with pytest.raises(ValueError, match="can't be edited"):
        papers.decide(row_id, True, {"citation": "Me 2026"})


def _europe_pmc(monkeypatch, open_access=True, fail=False):
    """Serve Europe PMC from a fake transport: one record (Riemensperger 2013),
    full text if open_access, a connection error if fail."""
    def handler(request):
        if fail:
            raise httpx.ConnectError("no route")
        if request.url.path.endswith("/search"):
            assert 'DOI:"10.1016/j.celrep.2012.12.014"' in request.url.params["query"]
            return httpx.Response(200, json={"resultList": {"result": [{
                "pmcid": "PMC1", "isOpenAccess": "Y" if open_access else "N", "doi": "10.1016/j.celrep.2012.12.014",
                "authorString": "Riemensperger T, Issa AR", "pubYear": "2013", "journalTitle": "Cell Rep",
                "title": "A single dopamine pathway", "abstractText": "Pink1 flies lose dopamine neurons. " * 10}]}})
        assert open_access, "full text fetched for a paper that isn't open access"
        return httpx.Response(200, text=f"<article><sec><p>{ABSTRACT}</p></sec></article>")

    monkeypatch.setattr(papers.httpx, "Client", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler)))


def test_doi_reads_the_open_access_full_text_and_keeps_the_real_citation(fake, monkeypatch):
    _europe_pmc(monkeypatch)
    sent = fake([_answer(_row(), citation="Clark et al. 2006, Nature")])   # the model misreads the paper
    out = papers.extract(doi="https://doi.org/10.1016/j.celrep.2012.12.014")

    assert ABSTRACT in sent.sent[0]["input"][0]["text"]
    assert out["citation"] == "Riemensperger et al. 2013, Cell Rep"
    assert out["url"] == "https://doi.org/10.1016/j.celrep.2012.12.014"
    assert out["read"] == "full text" and out["note"] is None
    assert out["rows"][0]["quote_found"] is True and out["rows"][0]["citation"] == out["citation"]


def test_doi_without_full_text_says_only_the_abstract_was_read(fake, monkeypatch):
    _europe_pmc(monkeypatch, open_access=False)
    fake([_answer(_row(clusters=[]))])
    out = papers.extract(doi="10.1016/j.celrep.2012.12.014")

    assert out["read"] == "abstract" and "Upload the PDF" in out["note"]
    assert any("Only the abstract" in p for p in out["rows"][0]["checks"]["problems"])


def test_a_pdf_takes_its_citation_from_the_doi_it_prints(fake, monkeypatch):
    pages = ["Cell Reports. doi: 10.1016/j.celrep.2012.12.014. " + "Title page. " * 50, "Results. " + ABSTRACT]
    monkeypatch.setattr(papers, "pdf_pages", lambda pdf: pages)
    _europe_pmc(monkeypatch)
    fake([_answer(_row(), citation="Clark et al. 2006, Nature")])
    assert papers.extract(b"%PDF-1.4", "r.pdf")["citation"] == "Riemensperger et al. 2013, Cell Rep"

    # Europe PMC down: fall back to what the model read.
    _europe_pmc(monkeypatch, fail=True)
    fake([_answer(_row(), citation="Riemensperger et al. 2013, Cell Reports")])
    out = papers.extract(b"%PDF-1.4", "r.pdf")
    assert out["citation"] == "Riemensperger et al. 2013, Cell Reports" and out["read"] == "PDF"


def test_rows_read_by_the_backup_model_are_flagged(fake, monkeypatch):
    fake([StatusError(503), _answer(_row())])
    out = papers.extract(text=ABSTRACT)
    assert out["fallback"] is True
    assert any("backup model" in p for p in out["rows"][0]["checks"]["problems"])


def test_inputs_are_checked_before_the_model_is_called(fake):
    fake([])
    with pytest.raises(ValueError, match="isn't a PDF"):
        papers.extract(b"hello", "notes.txt")
    with pytest.raises(ValueError, match="one of"):
        papers.extract()
    with pytest.raises(ValueError, match="too short"):
        papers.extract(text="PINK1 flies lose PPL1.")
    with pytest.raises(ValueError, match="DOI"):
        papers.extract(doi="not a doi")


def test_symbol_font_glyphs_are_read_as_text():
    text = "loss of TH/H11001 neurons in PAL, PPM1/H208622 and PPL1; doi/H2086210.1073/H20862pnas.0602493103"
    assert papers.clean_glyphs(text) == "loss of TH+ neurons in PAL, PPM1/2 and PPL1; doi/10.1073/pnas.0602493103"


def test_model_json_in_a_fence_is_accepted():
    assert papers.parse_json('```json\n{"rows": []}\n```') == {"rows": []}


def test_fallback_gets_only_the_time_left(fake, monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(papers, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(config, "PAPER_TIMEOUT_S", 150)
    monkeypatch.setattr(config, "PAPER_DEADLINE_S", 240)
    sent = fake([httpx.ReadTimeout("The read operation timed out"), _answer()])
    answer = sent.create

    def flash_hangs(**kwargs):
        if kwargs["model"] == config.AGENT_MODEL:
            clock.now += kwargs["timeout"]
        return answer(**kwargs)

    monkeypatch.setattr(sent, "create", flash_hangs)
    out = papers.extract(text=ABSTRACT)

    assert out["model"] == config.AGENT_FALLBACK_MODEL
    # Flash keeps its full 150s; the fallback gets the 90s left under the deadline.
    assert [(s["model"], s["timeout"]) for s in sent.sent] == [
        (config.AGENT_MODEL, 150), (config.AGENT_FALLBACK_MODEL, 90)]


def test_api_extract_and_decide(fake, monkeypatch):
    from fastapi.testclient import TestClient

    from neurosim.api.main import app

    client = TestClient(app)
    assert client.post("/evidence/extract").status_code == 400
    fake([_answer(_row())])
    row = client.post("/evidence/extract", data={"text": ABSTRACT}).json()["rows"][0]
    assert client.get("/evidence/proposals").json()[0]["id"] == row["id"]
    bad = client.post(f"/evidence/rows/{row['id']}/decision", json={"approve": True, "edits": {"tier": "x"}})
    assert bad.status_code == 400
    ok = client.post(f"/evidence/rows/{row['id']}/decision", json={"approve": True, "edits": {"clusters": ["PPL1", "PAM"]}})
    assert ok.json()["status"] == "approved" and ok.json()["clusters"] == ["PPL1", "PAM"]
    assert client.get("/evidence/approved").json()[0]["extracted"]["id"] == row["id"]
    assert client.delete(f"/evidence/approved/{row['id']}").status_code == 200
    assert client.delete(f"/evidence/approved/{row['id']}").status_code == 404


def _tiny_pdf(pages: list[str]) -> bytes:
    """A real PDF with one line of Helvetica text per page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 6 Tf 10 400 Td ({text}) Tj ET".encode()
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Contents {len(objs)} 0 R "
                    "/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out
