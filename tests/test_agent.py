"""Agent, run summary and paper extraction against a fake Gemini client, so
these run offline and cost no quota. The fake replays scripted interactions
and records what we sent."""

import json
from types import SimpleNamespace

import httpx
import pytest

from neurosim import config
from neurosim.agent import agent, gemini, papers, summary
from neurosim.api import mocks
from neurosim.models import SimulationRequest


def _call(name, args, id_="c1"):
    return SimpleNamespace(type="function_call", name=name, arguments=args, id=id_)


def _interaction(id_, steps=(), text=None):
    return SimpleNamespace(id=id_, steps=list(steps), output_text=text)


class StatusError(Exception):
    def __init__(self, status):
        super().__init__(f"error {status}")
        self.status_code = status
        self.body = {}


class FakeInteractions:
    def __init__(self, script):
        self.script = list(script)
        self.sent = []

    def create(self, **kwargs):
        self.sent.append(kwargs)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(config, "USE_MOCKS", True)
    monkeypatch.setattr(gemini, "_fallback_until", 0.0)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)

    def install(script):
        interactions = FakeInteractions(script)
        monkeypatch.setattr(gemini, "_client", SimpleNamespace(interactions=interactions))
        return interactions

    return install


def test_chat_runs_tools_and_returns_run_ids(fake):
    sent = fake([
        _interaction("i1", [_call("get_gene_chain", {"human_gene": "PRKN"}, "a"),
                            _call("run_simulation", {"human_gene": "PRKN"}, "b")]),
        _interaction("i2", text="PRKN hits the mushroom body (z 6.2)."),
    ])
    out = agent.chat("Knock out PRKN", context={"active_run": {"run_id": "mock-pink1-knockout"}})

    assert out["reply"].startswith("PRKN hits")
    assert out["run_ids"] == ["mock-prkn-knockout"]
    assert [c["name"] for c in out["tool_calls"]] == ["get_gene_chain", "run_simulation"]
    assert out["interaction_id"] == "i2"
    assert "mock-pink1-knockout" in sent.sent[0]["input"]          # workspace context reached the model
    results = sent.sent[1]["input"]
    assert [r["call_id"] for r in results] == ["a", "b"]           # all results together, matched by id
    assert sent.sent[1]["previous_interaction_id"] == "i1"


def test_tool_errors_go_back_to_the_model(fake):
    sent = fake([
        _interaction("i1", [_call("run_simulation", {"human_gene": "SNCA"})]),
        _interaction("i2", text="SNCA has no fly ortholog."),
    ])
    out = agent.chat("Run SNCA")
    assert out["run_ids"] == []
    assert "no fly ortholog" in out["tool_calls"][0]["error"]
    assert sent.sent[1]["input"][0]["is_error"] is True


def test_rate_limit_retries_once_then_falls_back(fake):
    sent = fake([StatusError(429), StatusError(429), _interaction("i1", text="ok")])
    out = agent.chat("hi")
    assert out["model"] == config.AGENT_FALLBACK_MODEL
    assert [s["model"] for s in sent.sent] == [config.AGENT_MODEL, config.AGENT_MODEL, config.AGENT_FALLBACK_MODEL]


def test_overload_falls_back_and_stays_there(fake):
    sent = fake([StatusError(503), _interaction("i1", text="ok"), _interaction("i2", text="ok")])
    agent.chat("hi")
    agent.chat("again", "i1")
    assert [s["model"] for s in sent.sent] == [config.AGENT_MODEL, config.AGENT_FALLBACK_MODEL, config.AGENT_FALLBACK_MODEL]


@pytest.mark.parametrize("timeout", [httpx.ReadTimeout("The read operation timed out"), TimeoutError()])
def test_timeout_falls_back_straight_away(fake, timeout):
    sent = fake([timeout, _interaction("i1", text="ok")])
    out = agent.chat("hi")
    assert out["reply"] == "ok"
    assert [s["model"] for s in sent.sent] == [config.AGENT_MODEL, config.AGENT_FALLBACK_MODEL]


def test_slow_turn_stops_at_the_deadline_with_a_readable_503(fake, monkeypatch):
    from fastapi.testclient import TestClient

    from neurosim.api.main import app

    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(agent, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(config, "AGENT_TURN_DEADLINE_S", 120.0)
    monkeypatch.setattr(config, "AGENT_REQUEST_TIMEOUT_S", 30)
    sent = fake([_interaction(f"i{n}", [_call("list_diseases", {}, f"c{n}")]) for n in range(1, 5)])
    answer = sent.create

    def slow(**kwargs):  # every Gemini call takes 50s
        clock.now += 50
        return answer(**kwargs)

    monkeypatch.setattr(sent, "create", slow)
    res = TestClient(app).post("/agent/chat", json={"message": "hi"})

    assert res.status_code == 503
    assert res.json()["detail"] == (
        "The agent couldn't finish within 2 minutes because Gemini is slow right now. Try again in a minute."
    )
    # Calls at t=0, 50 and 100 get the time left (capped at 30s); none starts at t=150.
    assert [s["timeout"] for s in sent.sent] == [30, 30, 20]


def test_refused_key_is_reported_plainly(fake):
    fake([StatusError(402)])
    with pytest.raises(gemini.GeminiUnavailable, match="billing"):
        agent.chat("hi")


def test_summary_uses_the_runs_numbers_and_drops_unknown_circuits(fake):
    result = mocks.mock_result(SimulationRequest(human_gene="PINK1"))
    summary._CACHE.clear()
    fake([_interaction("s1", text=json.dumps({
        "headline": "PINK1 seeds feed the mushroom body far more than chance.",
        "top_circuits": [
            {"group": "mushroom body", "level": "super_region", "why": "Most input comes from PPL1."},
            {"group": "made-up region", "level": "region", "why": "Invented."},
        ],
        "caveats": ["Sample numbers."],
        "next_experiment": {"description": "PPL101 alone", "why": "Find the bottleneck.",
                            "human_gene": "PINK1", "mode": "knockout", "seed_cell_types": ["PPL101"]},
    }))])
    out = summary.summarize_run(result)
    assert [c["group"] for c in out["top_circuits"]] == ["mushroom body"]
    assert out["top_circuits"][0]["z_score"] == 6.2
    assert out["next_experiment"]["request"]["seed_cell_types"] == ["PPL101"]


def test_paper_rows_wait_for_approval(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPROVED_EVIDENCE_PATH", tmp_path / "approved.json")
    row = {"disease": "parkinsons", "human_gene": "pink1", "fly_gene": "Pink1", "model_type": "RNAi",
           "clusters": ["PPL2"], "finding": "Pink1 RNAi lost PPL2 neurons.", "tier": "medium",
           "tier_reason": "Counted per cluster.", "quote": "PPL2 neurons were reduced", "page": 3}
    fake([_interaction("p1", text=json.dumps({"citation": "Wang et al. 2006, PNAS", "url": "", "rows": [row, row]}))])
    out = papers.extract(b"%PDF-1.4 fake", "wang.pdf")

    assert not config.APPROVED_EVIDENCE_PATH.exists()        # nothing saved before a decision
    first, second = out["rows"]
    assert first["human_gene"] == "PINK1" and first["status"] == "pending"
    papers.decide(first["id"], True)
    papers.decide(second["id"], False)
    saved = json.loads(config.APPROVED_EVIDENCE_PATH.read_text())["evidence"]
    assert len(saved) == 1
    assert saved[0]["verified_by_bio"] is False
    assert saved[0]["extracted"]["quote"] == "PPL2 neurons were reduced"


def test_paper_fallback_gets_only_the_time_left(fake, monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(papers, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(config, "PAPER_TIMEOUT_S", 150)
    monkeypatch.setattr(config, "PAPER_DEADLINE_S", 240)
    sent = fake([httpx.ReadTimeout("The read operation timed out"),
                 _interaction("p1", text=json.dumps({"citation": "", "url": "", "rows": []}))])
    answer = sent.create

    def flash_hangs(**kwargs):
        if kwargs["model"] == config.AGENT_MODEL:
            clock.now += kwargs["timeout"]
        return answer(**kwargs)

    monkeypatch.setattr(sent, "create", flash_hangs)
    out = papers.extract(b"%PDF-1.4 fake", "long.pdf")

    assert out["model"] == config.AGENT_FALLBACK_MODEL
    # Flash keeps its full 150s; the fallback gets the 90s left under the deadline.
    assert [(s["model"], s["timeout"]) for s in sent.sent] == [
        (config.AGENT_MODEL, 150), (config.AGENT_FALLBACK_MODEL, 90)]


def test_non_pdf_is_refused(fake):
    fake([])
    with pytest.raises(ValueError, match="isn't a PDF"):
        papers.extract(b"hello", "notes.txt")


def test_sdk_does_not_retry_on_its_own():
    # A local server that always fails: the SDK must give up after one request
    # and leave retrying to gemini.call.
    import http.server
    import threading

    from google import genai

    hits = []

    class Failing(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(self.path)
            self.rfile.read(int(self.headers.get("content-length", 0)))
            status = 429 if len(hits) == 1 else 503
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"code": status, "message": "busy"}}).encode())

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Failing)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        options = gemini.HTTP_OPTIONS.model_copy(update={"base_url": f"http://127.0.0.1:{server.server_port}"})
        client = genai.Client(api_key="test-key", http_options=options)
        for status in (429, 503):
            before = len(hits)
            with pytest.raises(Exception) as err:
                client.interactions.create(model="m", input="hi", timeout=5)
            assert gemini._status(err.value) == status
            assert len(hits) == before + 1
    finally:
        server.shutdown()
