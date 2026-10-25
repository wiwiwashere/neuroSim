"""User-supplied diseases: a CSV or typed rows in, checked rows out, saved
rows in the evidence table, seeds from the synthetic brain."""

import json

import pytest

from neurosim import config
from neurosim.bio import custom, evidence
from neurosim.engine.graph import set_connectome
from neurosim.engine.synthetic import synthetic_connectome
from neurosim.models import SimulationRequest


@pytest.fixture(autouse=True)
def synthetic_brain():
    set_connectome(synthetic_connectome())
    custom._catalogue_for.cache_clear()
    yield
    set_connectome(None)
    custom._catalogue_for.cache_clear()


def _a_cell_type() -> tuple[str, int]:
    """A non-dopamine cell type of the synthetic brain and its size."""
    name, info = max(((n, i) for n, i in custom.cell_type_catalogue().items() if i["n_dopamine"] == 0),
                     key=lambda x: x[1]["n_neurons"])
    return name, info["n_neurons"]


CSV = """disease,human_gene,fly_gene,affected,model_type,finding,citation,url,tier
Huntington's disease,HTT,htt,PAM; {cell_type},overexpression,"Expanded HTT, PAM lost","Smith et al. 2020",https://doi.org/x,high
Huntington's disease,PRKN,,PAM,RNAi,,,,
"""


def test_csv_rows_are_checked_saved_and_seed_a_run():
    cell_type, n = _a_cell_type()
    rows = custom.parse_upload("hd.csv", CSV.format(cell_type=cell_type).encode())
    assert rows[0]["affected"] == ["PAM", cell_type] and rows[1]["tier"] == "medium"

    out = custom.preview(rows, filename="hd.csv")
    assert out["disease"] == {"id": "huntingtons-disease", "name": "Huntington's disease"} and out["ok"], out
    first, second = out["rows"]
    kinds = {a["name"]: a for a in first["checks"]["affected"]}
    assert kinds["PAM"]["kind"] == "cluster" and kinds[cell_type] == {
        "name": cell_type, "kind": "cell_type", "match": "exact", "n_cell_types": 1, "n_neurons": n, "dopamine": False,
        "suggestions": []}
    assert first["checks"]["ortholog"]["user_supplied"] is True
    assert first["checks"]["confidence"] == round(config.UNSCORED_ORTHOLOG_CONFIDENCE * 0.9, 3)
    assert any("isn't a dopamine cell type" in note for note in first["checks"]["notes"])
    # PRKN is in the table, so its ortholog comes from there.
    assert second["checks"]["ortholog"] == {"known": True, "fly_genes": ["park"], "confidence": evidence.find_ortholog("PRKN").confidence,
                                            "user_supplied": False}

    saved = custom.save(rows, filename="hd.csv")
    assert saved["id"] == "huntingtons-disease" and saved["genes"] == ["HTT", "PRKN"]
    assert config.CUSTOM_DISEASES_PATH.exists()

    # In the picker, with the user's ortholog, and PRKN listed for both diseases.
    assert evidence.list_diseases() == ["huntingtons-disease", "parkinsons"]
    genes = {g["human_gene"]: g for g in evidence.list_genes("huntingtons-disease")}
    assert genes["HTT"]["fly_genes"] == ["htt"] and genes["HTT"]["simulatable"] and genes["HTT"]["best_tier"] == "high"
    assert genes["PRKN"]["simulatable"]
    assert "HTT" not in {g["human_gene"] for g in evidence.list_genes("parkinsons")}

    seeds = evidence.resolve_seeds(SimulationRequest(human_gene="HTT"))
    assert seeds.disease == "huntingtons-disease" and seeds.user_supplied is True
    by_type = {t.cell_type: t for t in seeds.seed_types}
    assert by_type[cell_type].n_neurons == n and by_type[cell_type].cluster == cell_type
    assert any(t.cluster == "PAM" for t in seeds.seed_types)
    assert all(e.user_supplied and e.user_supplied.disease_id == "huntingtons-disease" for t in seeds.seed_types for e in t.evidence)

    # PRKN under the custom disease keeps only its custom row (PAM); under Parkinson's, only the built-in one (PPL1).
    hd = evidence.resolve_seeds(SimulationRequest(human_gene="PRKN", disease="huntingtons-disease"))
    assert {t.cluster for t in hd.seed_types} == {"PAM"} and hd.user_supplied
    pd = evidence.resolve_seeds(SimulationRequest(human_gene="PRKN", disease="parkinsons"))
    assert {t.cluster for t in pd.seed_types} == {"PPL1"} and not pd.user_supplied
    assert all(e.user_supplied is None for t in pd.seed_types for e in t.evidence)
    with pytest.raises(evidence.SeedError, match="only for other diseases"):
        evidence.resolve_seeds(SimulationRequest(human_gene="HTT", disease="parkinsons"))

    # Saving again with the same name replaces it; removing takes everything out.
    custom.save(rows[:1], filename="hd.csv")
    assert custom.list_custom()[0]["n_rows"] == 1
    custom.remove("huntingtons-disease")
    assert evidence.list_diseases() == ["parkinsons"]
    with pytest.raises(evidence.SeedError):
        evidence.resolve_seeds(SimulationRequest(human_gene="HTT"))


def test_problems_block_the_save():
    rows = [
        {"gene": "NOTAGENE", "affected": "PPL1"},                     # no ortholog given
        {"human_gene": "PINK1", "affected": "PPL1; Nonsense99"},     # unknown name
        {"human_gene": "PRKN", "affected": []},                      # nothing affected
        {"human_gene": "PINK1", "affected": "PPL1"},                 # fine on its own
        {"human_gene": "PINK1", "affected": "ppl1"},                 # same again
    ]
    out = custom.preview(rows, "My ALS")
    problems = [r["checks"]["problems"] for r in out["rows"]]
    assert "fly ortholog" in problems[0][0]
    assert "Nonsense99" in problems[1][0]
    assert "seeds nothing" in problems[2][0]
    assert "twice" in problems[3][0] and "twice" in problems[4][0]
    assert out["rows"][4]["affected"] == ["ppl1"] and out["rows"][4]["checks"]["affected"][0]["name"] == "PPL1"
    assert not out["ok"]
    with pytest.raises(custom.CustomError, match="Fix these first"):
        custom.save(rows, "My ALS")
    assert not config.CUSTOM_DISEASES_PATH.exists()

    bad = custom.preview([{"human_gene": "PINK1", "affected": "PPL1"}], "Parkinsons")
    assert any("built-in" in p for p in bad["problems"])
    assert not custom.preview([{"human_gene": "PINK1", "affected": "PPL1"}])["ok"]   # no name anywhere


def test_duplicate_of_a_saved_row_is_flagged():
    custom.save([{"human_gene": "PINK1", "affected": "PPL1"}], "Thing")
    again = custom.preview([{"human_gene": "PINK1", "affected": "PPL1"}], "Thing")
    assert again["ok"]   # re-saving the same disease replaces it, so no duplicate
    other = custom.preview([{"human_gene": "PINK1", "affected": "PPL1"}], "Thing two")
    assert other["ok"]   # a different disease may say the same


def test_json_upload_and_templates_round_trip():
    tmpl = custom.template_json()
    data = json.dumps({"disease": tmpl["disease"], "rows": tmpl["rows"]}).encode()
    rows = custom.parse_upload("t.json", data)
    assert rows[0]["disease"] == "Huntington's disease" and rows[0]["affected"] == ["PAM", "MBON01"]
    csv_rows = custom.parse_upload("t.csv", custom.template_csv().encode())
    assert [r["affected"] for r in csv_rows] == [r["affected"] for r in rows]
    with pytest.raises(custom.CustomError, match="header"):
        custom.parse_upload("x.csv", b"a,b\n1,2\n")
    with pytest.raises(custom.CustomError, match="empty"):
        custom.parse_upload("x.csv", b"")


def test_unknown_names_get_suggestions_and_search_finds_types():
    cell_type, n = _a_cell_type()
    found = custom.resolve_name(cell_type.lower())
    assert found["name"] == cell_type and found["n_neurons"] == n
    assert custom.resolve_name("PPL-1")["name"] == "PPL1"
    typo = custom.resolve_name(cell_type[:-1] + "zz" if len(cell_type) > 3 else "PPL9")
    assert typo["kind"] == "unknown"
    hits = custom.search_names(cell_type[:3])
    assert any(h["name"] == cell_type for h in hits)
    assert custom.search_names("PP")[0]["kind"] == "cluster"


def test_api_round_trip_in_mock_mode(monkeypatch):
    """Upload, review, save, pick, run, remove, over HTTP with the API on mocks
    (seeds are still real when a connectome is loaded)."""
    import importlib

    from fastapi.testclient import TestClient

    from neurosim.agent import tools

    monkeypatch.setenv("NEUROSIM_MOCKS", "1")
    import neurosim.api.main as main

    client = TestClient(importlib.reload(main).app)
    cell_type, n = _a_cell_type()

    assert client.get("/custom/template.csv").text.startswith("disease,human_gene")
    assert "rows" in client.get("/custom/template.json").json()
    assert client.get("/custom/names", params={"q": cell_type[:3]}).json()

    csv_bytes = CSV.format(cell_type=cell_type).encode()
    preview = client.post("/custom/preview", files={"file": ("hd.csv", csv_bytes, "text/csv")})
    assert preview.status_code == 200 and preview.json()["ok"], preview.text
    rows = preview.json()["rows"]

    bad = client.post("/custom/diseases", json={"name": "HD", "file": "hd.csv", "rows": [{"human_gene": "HTT", "affected": "PAM"}]})
    assert bad.status_code == 400 and "fly ortholog" in bad.json()["detail"]

    # The reviewed rows go back as they are (checks and all); the server re-checks them.
    saved = client.post("/custom/diseases", json={"name": "Huntington's disease", "file": "hd.csv", "rows": rows})
    assert saved.status_code == 200, saved.text
    assert client.get("/diseases").json() == ["huntingtons-disease", "parkinsons"]
    assert client.get("/custom/diseases").json()[0]["genes"] == ["HTT", "PRKN"]
    genes = {g["human_gene"]: g for g in client.get("/diseases/huntingtons-disease/genes").json()}
    assert genes["HTT"]["simulatable"]

    chain = client.get("/genes/HTT/chain", params={"disease": "huntingtons-disease"}).json()
    assert chain["user_supplied"] is True and {t["cell_type"] for t in chain["seed_types"]} >= {cell_type}
    run = client.post("/simulate", json={"human_gene": "HTT", "disease": "huntingtons-disease"}).json()
    assert run["run_id"] == "mock-htt-knockout-huntingtons-disease" and run["seeds"]["user_supplied"]
    targets = client.get("/genes/HTT/targets", params={"disease": "huntingtons-disease"}).json()
    if targets is not None:   # Kait's one-hop table is on disk: PAM has a column, the cell type has none
        assert targets["clusters"] == ["PAM"] and targets["clusters_not_covered"] == [cell_type]

    # The agent sees it too.
    monkeypatch.setattr(config, "USE_MOCKS", True)
    listed = json.loads(tools.list_diseases())["diseases"]
    assert {d["id"]: d["user_supplied"] for d in listed} == {"huntingtons-disease": True, "parkinsons": False}
    assert json.loads(tools.get_gene_chain("htt", disease="huntingtons-disease"))["user_supplied"] is True
    out = json.loads(tools.run_simulation("HTT", disease="huntingtons-disease"))
    assert out["request"]["disease"] == "huntingtons-disease" and out["request"]["user_supplied"] is True

    assert client.delete("/custom/diseases/huntingtons-disease").json() == {"removed": "huntingtons-disease"}
    assert client.delete("/custom/diseases/huntingtons-disease").status_code == 404
    assert client.get("/diseases").json() == ["parkinsons"]
