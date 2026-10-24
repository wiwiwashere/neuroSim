"""The Gemma path (config.LLM = "gemma") against a fake generate_content, so
these run offline and cost no quota. The fake replays scripted responses and
records what we sent."""

import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

from neurosim import config
from neurosim.agent import agent, gemini, gemma, papers, summary
from neurosim.api import mocks
from neurosim.models import SimulationRequest


def _response(*parts):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
    )


def _call(name, args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def _text(text, thought=False):
    return types.Part(text=text, thought=thought or None)


class FakeModels:
    def __init__(self, script):
        self.script = list(script)
        self.sent = []

    def generate_content(self, **kwargs):
        # The agent appends to its history list after the call; keep what was sent.
        self.sent.append({**kwargs, "contents": list(kwargs["contents"]) if isinstance(kwargs["contents"], list) else kwargs["contents"]})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(config, "LLM", "gemma")
    monkeypatch.setattr(config, "LLM_NAME", "Gemma")
    monkeypatch.setattr(config, "AGENT_MODEL", "gemma-4-31b-it")
    monkeypatch.setattr(config, "AGENT_FALLBACK_MODEL", "gemma-4-26b-a4b-it")
    monkeypatch.setattr(config, "USE_MOCKS", True)
    monkeypatch.setattr(gemini, "_fallback_until", 0.0)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)

    def install(script):
        models = FakeModels(script)
        monkeypatch.setattr(gemini, "_client", SimpleNamespace(models=models))
        return models

    return install


def test_chat_runs_tools_and_keeps_the_history(fake):
    sent = fake([
        _response(_text("I should check the chain first.", thought=True),
                  _call("get_gene_chain", {"human_gene": "PRKN"}), _call("run_simulation", {"human_gene": "PRKN"})),
        _response(_text("PRKN hits the mushroom body (z 6.2).")),
        _response(_text("PINK1 overlaps with it.")),
    ])
    out = agent.chat("Knock out PRKN", context={"active_run": {"run_id": "mock-pink1-knockout"}})

    assert out["reply"] == "PRKN hits the mushroom body (z 6.2)."
    assert out["run_ids"] == ["mock-prkn-knockout"]
    assert [c["name"] for c in out["tool_calls"]] == ["get_gene_chain", "run_simulation"]
    assert out["model"] == "gemma-4-31b-it"
    assert out["interaction_id"].startswith("gemma-")

    first, second = sent.sent[:2]
    assert first["model"] == "gemma-4-31b-it"
    assert "mock-pink1-knockout" in first["contents"][0].parts[0].text      # workspace context reached the model
    assert first["config"].system_instruction == agent.SYSTEM_PROMPT
    assert {d.name for d in first["config"].tools[0].function_declarations} == set(agent.TOOLS)
    assert first["config"].thinking_config.thinking_level == types.ThinkingLevel.HIGH
    # The second call resends the question, the model's calls, and both results together.
    results = second["contents"][2]
    assert [p.function_response.name for p in results.parts] == ["get_gene_chain", "run_simulation"]
    assert "result" in results.parts[1].function_response.response

    # The next turn picks the history up from the id.
    again = agent.chat("And PINK1?", out["interaction_id"])
    assert len(sent.sent[2]["contents"]) == 5
    assert again["interaction_id"] != out["interaction_id"]


def test_tool_errors_go_back_to_the_model(fake):
    sent = fake([_response(_call("run_simulation", {"human_gene": "SNCA"})), _response(_text("SNCA has no fly ortholog."))])
    out = agent.chat("Run SNCA")
    assert out["run_ids"] == []
    assert "no fly ortholog" in out["tool_calls"][0]["error"]
    assert "no fly ortholog" in sent.sent[1]["contents"][2].parts[0].function_response.response["error"]


def test_last_round_must_answer_in_text(fake, monkeypatch):
    monkeypatch.setattr(config, "AGENT_MAX_TOOL_ROUNDS", 2)
    sent = fake([_response(_call("list_diseases", {})), _response(_call("list_diseases", {})), _response(_text("Parkinson's."))])
    out = agent.chat("hi")
    assert out["reply"] == "Parkinson's."
    modes = [s["config"].tool_config.function_calling_config.mode for s in sent.sent]
    assert modes == [types.FunctionCallingConfigMode.AUTO, types.FunctionCallingConfigMode.AUTO,
                     types.FunctionCallingConfigMode.NONE]


def test_unknown_or_gemini_id_starts_a_new_conversation(fake):
    sent = fake([_response(_text("ok"))])
    agent.chat("hi", "v1_some-gemini-interaction")
    assert len(sent.sent[0]["contents"]) == 1


def test_overload_falls_back_to_the_moe_model(fake):
    class Busy(Exception):
        code = 503

    sent = fake([Busy("busy"), _response(_text("ok"))])
    out = agent.chat("hi")
    assert out["model"] == "gemma-4-26b-a4b-it"
    assert [s["model"] for s in sent.sent] == ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]


def test_timeouts_reach_the_sdk_in_milliseconds(fake, monkeypatch):
    monkeypatch.setattr(config, "AGENT_REQUEST_TIMEOUT_S", 30)
    sent = fake([httpx.ReadTimeout("The read operation timed out"), _response(_text("ok"))])
    agent.chat("hi")
    assert sent.sent[0]["config"].http_options.timeout == 30_000
    assert sent.sent[0]["config"].http_options.retry_options.attempts == 1


def test_summary_parses_fenced_json_and_skips_thinking(fake):
    result = mocks.mock_result(SimulationRequest(human_gene="PINK1"))
    summary._CACHE.clear()
    body = {
        "headline": "PINK1 seeds feed the mushroom body far more than chance.",
        "top_circuits": [{"group": "mushroom body", "level": "super_region", "why": "Most input comes from PPL1."}],
        "caveats": ["Sample numbers."],
        "next_experiment": {"description": "PPL101 alone", "why": "Find the bottleneck.",
                            "human_gene": "PINK1", "mode": "knockout", "seed_cell_types": ["PPL101"]},
    }
    sent = fake([_response(_text("{not this}", thought=True), _text(f"```json\n{json.dumps(body)}\n```"))])
    out = summary.summarize_run(result)

    assert out["top_circuits"][0]["z_score"] == 6.2
    assert out["model"] == "gemma-4-31b-it"
    cfg = sent.sent[0]["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema == summary.SCHEMA
    assert '"headline"' in cfg.system_instruction                     # schema also spelled out in the prompt
    assert cfg.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL


def test_summary_that_isnt_json_is_a_readable_error(fake):
    summary._CACHE.clear()
    fake([_response(_text("Sorry, I can't."))])
    with pytest.raises(gemini.GeminiUnavailable, match="Gemma returned a summary that isn't valid JSON"):
        summary.summarize_run(mocks.mock_result(SimulationRequest(human_gene="PINK1")))


def test_paper_text_goes_to_generate_content(fake):
    quote = "Aged Pink1 RNAi flies showed a significant loss of PPL1 cluster dopaminergic neurons"
    row = {"disease": "parkinsons", "human_gene": "pink1", "fly_gene": "Pink1", "model_type": "RNAi",
           "clusters": ["PPL1"], "finding": "Pink1 RNAi flies lose PPL1 neurons.", "tier": "medium",
           "tier_reason": "Loss reported without per-cluster counts.", "quote": quote, "page": 0}
    sent = fake([_response(_text(json.dumps({"citation": "Doe et al. 2020, Fly Journal", "url": "", "rows": [row]})))])
    out = papers.extract(text=f"Here we knocked down Pink1 in Drosophila dopaminergic neurons by RNAi. {quote} "
                              "compared with controls, while the PAM cluster was unaffected. " * 3)

    assert [r["human_gene"] for r in out["rows"]] == ["PINK1"]
    assert out["rows"][0]["quote_found"] is True
    assert out["model"] == "gemma-4-31b-it"
    prompt = sent.sent[0]["contents"]
    assert isinstance(prompt, str) and quote in prompt
    cfg = sent.sent[0]["config"]
    assert cfg.response_mime_type == "application/json"
    assert "rows" in cfg.response_json_schema["properties"]


def test_generate_content_does_not_retry_on_its_own():
    # The per-request http_options replaces the client's; the SDK must still
    # give up after one request and leave retrying to gemini.call.
    import http.server
    import threading

    from google import genai

    hits = []

    class Failing(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(self.path)
            self.rfile.read(int(self.headers.get("content-length", 0)))
            self.send_response(503)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"code": 503, "message": "busy"}}).encode())

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Failing)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        client = genai.Client(api_key="test-key", http_options=gemini.HTTP_OPTIONS.model_copy(update={"base_url": base}))
        cfg = gemma.generation_config("sys", thinking_level="low", max_output_tokens=10, timeout=5)
        cfg.http_options = cfg.http_options.model_copy(update={"base_url": base})
        with pytest.raises(Exception) as err:
            client.models.generate_content(model="gemma-4-31b-it", contents="hi", config=cfg)
        assert gemini._status(err.value) == 503
        assert len(hits) == 1
    finally:
        server.shutdown()


def test_api_names_the_model_family(monkeypatch):
    from fastapi.testclient import TestClient

    from neurosim.api.main import app

    monkeypatch.setattr(config, "LLM", "gemma")
    monkeypatch.setattr(config, "LLM_NAME", "Gemma")
    monkeypatch.setattr(config, "AGENT_MODEL", "gemma-4-31b-it")
    body = TestClient(app).get("/agent/llm").json()
    assert (body["family"], body["name"], body["model"]) == ("gemma", "Gemma", "gemma-4-31b-it")
