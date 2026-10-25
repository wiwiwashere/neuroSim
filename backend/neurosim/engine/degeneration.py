"""Neurodegeneration time-series for the 3D connectome view.

Strategy:
  1. Build a small structural coupling matrix from the top-N most-impacted
     regions on a completed SimulationResult (subgraph region labels, which
     match GraphNode.group so the frontend can colour neurons directly).
  2. Run a Wilson–Cowan neural mass (neurolib WCModel when installed, else a
     matching numpy integrator). WC is used instead of ALNModel for speed.
  3. In each frame, reduce excitatory drive to seed-containing regions
     linearly, simulating progressive neuron loss.
  4. Return activity[t, region] as DegenerationFrame objects.

This is NOT biologically precise — it is a plausible visual narrative of
"what if these neurons degraded over weeks/months".
"""

from __future__ import annotations

import numpy as np

from neurosim.engine import pipeline
from neurosim.models import DegenerationFrame, DegenerationSeries, GroupLevel, SankeyLink, Subgraph

N_FRAMES = 60  # 6 fps × 10 s wall-clock at T=10


def run_dynamics(run_id: str, n_regions: int = 10, T: float = 10.0) -> DegenerationSeries:
    """Wilson–Cowan time-series as seed regions lose drive over simulated time T."""
    result = pipeline.get_result(run_id)
    graph = pipeline.get_subgraph(run_id)
    try:
        sankey = pipeline.get_sankey(run_id)
    except KeyError:
        sankey = []
    return _series_for(run_id, graph, result.groups.get(GroupLevel.REGION) or result.groups.get(GroupLevel.SUPER_REGION) or [], sankey, n_regions, T)


def _series_for(run_id: str, graph: Subgraph, groups, sankey: list[SankeyLink], n_regions: int, T: float) -> DegenerationSeries:
    n_regions = max(1, int(n_regions))
    T = float(T)
    names = _region_names(graph, groups, n_regions)
    n = len(names)
    Cmat = _coupling(names, graph, sankey)
    Dmat = np.zeros((n, n), dtype=float)
    seed_idx = _seed_indices(names, graph)
    n_frames = N_FRAMES if T > 0 else 1
    dt = T / (n_frames - 1) if n_frames > 1 else 0.0
    drive = np.stack([_drive(n, seed_idx, 1.0 - (i / (n_frames - 1) if n_frames > 1 else 0.0)) for i in range(n_frames)])
    activity, model = _integrate_wc(Cmat, Dmat, drive)
    frames = []
    for i in range(n_frames):
        health = 1.0 - (i / (n_frames - 1) if n_frames > 1 else 0.0)
        raw = {names[j]: float(activity[i, j]) for j in range(n)}
        frames.append(DegenerationFrame(t=i * dt, region_activity=_normalise_frame(raw), seed_health=health))
    return DegenerationSeries(run_id=run_id, frames=frames, dt=dt, total_t=T, n_regions=n, model=model)


def _region_names(graph: Subgraph, groups, n_regions: int) -> list[str]:
    """Prefer subgraph groups (same strings as GraphNode.group), ranked by impact."""
    from collections import defaultdict

    by_group: dict[str, list[float]] = defaultdict(list)
    for node in graph.nodes:
        by_group[node.group].append(node.impact if not node.is_seed else 1.0)
    ranked = sorted(by_group, key=lambda g: -sum(by_group[g]) / len(by_group[g]))
    if not ranked:
        ranked = [g.group for g in groups]
    names = ranked[:n_regions] or ["unknown"]
    return names


def _coupling(names: list[str], graph: Subgraph, sankey: list[SankeyLink]) -> np.ndarray:
    n = len(names)
    idx = {name: i for i, name in enumerate(names)}
    C = np.zeros((n, n), dtype=float)
    group_of = {node.id: node.group for node in graph.nodes}
    for edge in graph.edges:
        src, tgt = group_of.get(edge.source), group_of.get(edge.target)
        if src in idx and tgt in idx and src != tgt:
            C[idx[tgt], idx[src]] += max(edge.weight, 0.0)
    if float(C.sum()) == 0.0 and sankey:
        inflow = np.zeros(n, dtype=float)
        for link in sankey:
            if link.target in idx:
                inflow[idx[link.target]] += link.value
        C = np.outer(inflow, inflow)
        np.fill_diagonal(C, 0.0)
    if float(C.sum()) == 0.0:
        C = np.ones((n, n), dtype=float) * 0.15
        np.fill_diagonal(C, 0.0)
    row = C.sum(axis=1, keepdims=True)
    row[row == 0] = 1.0
    return C / row


def _seed_indices(names: list[str], graph: Subgraph) -> list[int]:
    seed_groups = {node.group for node in graph.nodes if node.is_seed}
    idx = [i for i, name in enumerate(names) if name in seed_groups]
    return idx or [0]


def _drive(n: int, seed_idx: list[int], seed_health: float) -> np.ndarray:
    P = np.full(n, 0.85, dtype=float)
    for i in seed_idx:
        P[i] = 0.35 + 1.1 * seed_health
    return P


def _normalise_frame(raw: dict[str, float]) -> dict[str, float]:
    vals = list(raw.values())
    lo, hi = min(vals), max(vals)
    span = hi - lo
    if span < 1e-9:
        return {k: 0.5 for k in raw}
    return {k: (v - lo) / span for k, v in raw.items()}


def _integrate_wc(Cmat: np.ndarray, Dmat: np.ndarray, drive: np.ndarray) -> tuple[np.ndarray, str]:
    try:
        return _neurolib_wc(Cmat, Dmat, drive), "WCModel"
    except Exception:
        return _numpy_wc(Cmat, drive), "WCModel"


def _neurolib_wc(Cmat: np.ndarray, Dmat: np.ndarray, drive: np.ndarray) -> np.ndarray:
    from neurolib.models.wc import WCModel

    model = WCModel(Cmat=np.asarray(Cmat, dtype=float), Dmat=np.asarray(Dmat, dtype=float))
    model.params["duration"] = 80.0
    model.params["dt"] = 0.1
    model.params["sigma_ou"] = 0.0
    frames = []
    for ext in drive:
        model.params["exc_ext"] = np.asarray(ext, dtype=float)
        model.run()
        frames.append(np.mean(np.asarray(model.exc), axis=1))
    return np.vstack(frames)


def _numpy_wc(Cmat: np.ndarray, drive: np.ndarray, steps_per_frame: int = 25) -> np.ndarray:
    """Wilson–Cowan Euler step, same role as neurolib.models.wc.WCModel."""
    n = Cmat.shape[0]
    E = np.full(n, 0.25)
    I = np.full(n, 0.15)
    tau_e, tau_i = 2.5, 3.5
    a_ee, a_ei, a_ie, a_ii = 12.0, 9.0, 10.0, 3.0
    dt = 0.05
    out = np.zeros((len(drive), n))
    for k, P in enumerate(drive):
        for _ in range(steps_per_frame):
            coupl = Cmat @ E
            E = np.clip(E + dt * (-E + _sig(a_ee * coupl - a_ei * I + P)) / tau_e, 0.0, 1.0)
            I = np.clip(I + dt * (-I + _sig(a_ie * coupl - a_ii * I)) / tau_i, 0.0, 1.0)
        out[k] = E
    return out


def _sig(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))
