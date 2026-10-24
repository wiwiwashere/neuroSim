"""The PAM -> beta-prime validation must pass on the synthetic brain, where the
answer is wired in. On real data the same script is the demo's credibility check."""

from neurosim.engine import pipeline
from neurosim.engine.graph import set_connectome
from neurosim.engine.validation import main

from engine_status import needs_engine


@needs_engine
def test_validation_recovers_the_planted_pam_result(capsys):
    try:
        assert main(["--synthetic"]) == 0
    finally:
        set_connectome(None)
        pipeline.clear_cache()
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert "beta-prime MBONs" in out
