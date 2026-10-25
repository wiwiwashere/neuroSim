"""Wilson–Cowan degeneration series: mocks and the numpy integrator."""

from neurosim.api import mocks
from neurosim.engine.degeneration import N_FRAMES, _numpy_wc, _series_for
from neurosim.models import GroupLevel
import numpy as np


def test_mock_dynamics_decays_from_healthy_to_lost():
    series = mocks.mock_dynamics("mock-prkn-knockout", n_regions=10, T=10.0)
    assert series.model == "WCModel"
    assert series.n_regions >= 1
    assert len(series.frames) == 60
    assert series.frames[0].seed_health == 1.0
    assert series.frames[-1].seed_health == 0.0
    assert series.total_t == 10.0
    assert "MB_ML_R" in series.frames[0].region_activity


def test_wc_series_from_subgraph_has_normalised_activity():
    graph = mocks.mock_subgraph()
    groups = mocks.mock_result().groups[GroupLevel.REGION]
    series = _series_for("run", graph, groups, mocks.mock_sankey(), n_regions=3, T=10.0)
    assert series.n_regions == 3
    assert len(series.frames) == N_FRAMES
    first = series.frames[0].region_activity
    last = series.frames[-1].region_activity
    assert set(first) == set(last)
    for frame in series.frames:
        vals = list(frame.region_activity.values())
        assert min(vals) >= 0.0 and max(vals) <= 1.0
        assert 0.0 <= frame.seed_health <= 1.0


def test_numpy_wc_activity_drops_when_seed_drive_falls():
    C = np.array([[0.0, 0.4], [0.6, 0.0]])
    healthy = np.array([[1.4, 0.85], [1.4, 0.85]])
    sick = np.array([[0.35, 0.85], [0.35, 0.85]])
    e0 = _numpy_wc(C, healthy)
    e1 = _numpy_wc(C, sick)
    assert e1[-1, 0] < e0[-1, 0]
