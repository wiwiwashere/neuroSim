"""HTTP-level behaviour of the FastAPI app."""

from fastapi.testclient import TestClient

from neurosim.agent import agent
from neurosim.api.main import app


def test_unhandled_error_is_json_with_a_readable_detail(monkeypatch):
    def boom(*args):
        raise RuntimeError("bug")

    monkeypatch.setattr(agent, "chat", boom)
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post("/agent/chat", json={"message": "Test PPL101 alone"})
    assert res.status_code == 500
    assert res.json() == {"detail": "neuroSim hit an internal error (RuntimeError). The API log has the traceback."}
