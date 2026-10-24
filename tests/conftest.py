import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


@pytest.fixture(autouse=True)
def _no_local_uploads(tmp_path, monkeypatch):
    # Rows someone approved in the running app must not leak into the tests.
    from neurosim import config

    monkeypatch.setattr(config, "APPROVED_EVIDENCE_PATH", tmp_path / "evidence_approved.json")
    monkeypatch.setattr(config, "PROPOSALS_PATH", tmp_path / "evidence_proposals.json")
    monkeypatch.setattr("neurosim.agent.papers._PROPOSALS", None)
