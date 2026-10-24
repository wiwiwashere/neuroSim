"""One call that runs a whole experiment (CS1). The API and the agent only
ever call functions in this file.

run_simulation(request) does, in order:
    1. seeds  = bio.evidence.resolve_seeds(request)          gene -> SeedSet
    2. x0     = perturb.initial_deficit(...)                  deficit at seeds
    3. prop   = propagate.propagate(A, x0, hops, decay)       per-neuron impact
    4. groups = vulnerability.group_table(...) per level      ranked groups
    5. null   = baseline.null_distribution(...)               200 random DA draws
    6. stats  = baseline.z_and_p + benjamini_hochberg         z, p, q per group
    7. D      = vulnerability.disruption_score(...) + its z
    8. pack everything into a SimulationResult, including config values used

Results are cached by run_id = hash of the request fields + config values.
Same request, same answer, instantly. That is what makes the live demo safe.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np

from neurosim import config
from neurosim.bio import evidence
from neurosim.engine import baseline, compare as compare_mod, subgraph, vulnerability
from neurosim.engine.graph import Connectome, load_connectome
from neurosim.engine.perturb import initial_deficit
from neurosim.engine.propagate import Propagation, propagate
from neurosim.models import (
    Comparison,
    GroupLevel,
    GroupScore,
    NeuronImpact,
    SankeyLink,
    SeedSet,
    SimulationRequest,
    SimulationResult,
    Subgraph,
)

TOP_NEURONS = 50
LABELLED_LEVELS = (GroupLevel.REGION, GroupLevel.SUPER_REGION)


@dataclass
class _RunState:
    """What the drawing endpoints need after a run, kept next to the result."""

    conn: Connectome
    seeds: SeedSet
    seed_positions: np.ndarray
    x0: np.ndarray
    prop: Propagation
    sankey: list[SankeyLink] | None = None
    subgraph: Subgraph | None = None


_RESULTS: dict[str, SimulationResult] = {}
_STATE: dict[str, _RunState] = {}


def _config_values() -> dict:
    return {
        "synapse_threshold": config.SYNAPSE_THRESHOLD,
        "n_random_draws": config.N_RANDOM_DRAWS,
        "random_seed": config.RANDOM_SEED,
        "min_group_size": config.MIN_GROUP_SIZE,
        "strong_hit": config.STRONG_HIT,
        "fdr_alpha": config.FDR_ALPHA,
    }


def run_id_for(request: SimulationRequest, seeds: SeedSet | None = None, conn: Connectome | None = None) -> str:
    """Deterministic short hash of the request and the relevant config values.

    The seed root IDs and the connectome's size go in too, so an edit to
    evidence.json or a different dataset can never return a stale cached run.
    """
    payload = {"request": request.model_dump(mode="json"), "config": _config_values()}
    if seeds is not None:
        payload["seeds"] = sorted(seeds.root_ids)
    if conn is not None:
        payload["connectome"] = [conn.source, conn.n, int(conn.W.nnz), float(conn.W.sum())]
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:10]
    return f"{request.human_gene.lower()}-{request.mode.value}-{digest}"


def run_simulation(request: SimulationRequest, seeds: SeedSet | None = None) -> SimulationResult:
    """Run one experiment, or return it from the cache. `seeds` overrides the
    evidence chain (the validation script passes the Riemensperger PAM set)."""
    conn = load_connectome()
    seeds = seeds or evidence.resolve_seeds(request)
    run_id = run_id_for(request, seeds, conn)
    if run_id in _RESULTS:
        return _RESULTS[run_id]

    seed_positions = np.unique(conn.positions(seeds.root_ids))
    x0 = initial_deficit(conn.n, seed_positions, request.mode, request.strength)
    prop = propagate(conn.A, x0, request.hops, request.decay)

    pool = conn.dopaminergic()
    groupings, tables = {}, {}
    for level in GroupLevel:
        codes, names = vulnerability.group_codes(conn.neurons, level)
        groupings[level] = (codes, len(names))
        tables[level] = (names, vulnerability.group_table(prop, conn.neurons, level, config.MIN_GROUP_SIZE,
                                                          config.STRONG_HIT))
    null_means, null_disruption = baseline.null_distributions(
        conn, len(seed_positions), request.mode, request.strength, request.hops, request.decay, groupings, pool)

    groups = {level: _score_groups(level, *tables[level], null_means[level], conn) for level in GroupLevel}

    disruption = vulnerability.disruption_score(prop, conn.in_strength, request.hops, request.decay)
    d_mean, d_sd, d_z, _ = baseline.z_and_p(np.array([disruption]), null_disruption[None, :])
    reached = (prop.impact > 0) & ~prop.seed_mask

    result = SimulationResult(
        run_id=run_id,
        request=request,
        seeds=seeds,
        n_seed_neurons=len(seed_positions),
        n_reached=int(reached.sum()),
        disruption_score=disruption,
        disruption_null_mean=float(d_mean[0]),
        disruption_z=float(d_z[0]),
        groups=groups,
        top_neurons=_top_neurons(conn, prop),
        assumptions={
            **_config_values(),
            "hops": request.hops,
            "decay": request.decay,
            "mode": request.mode.value,
            "strength": request.strength if request.mode.value != "knockout" else 1.0,
            "null": f"random DA neurons x{config.N_RANDOM_DRAWS} (pool of {len(pool)})",
            "connectome": conn.source,
        },
    )
    _RESULTS[run_id] = result
    _STATE[run_id] = _RunState(conn=conn, seeds=seeds, seed_positions=seed_positions, x0=x0, prop=prop)
    return result


def _score_groups(level: GroupLevel, names: list[str], table, null: np.ndarray, conn: Connectome) -> list[GroupScore]:
    """Attach null statistics to one level's group table. Only rankable groups
    are returned, sorted by z descending."""
    code = {name: i for i, name in enumerate(names)}
    table = table[table["rankable"]]
    if table.empty:
        return []
    codes = table["group"].map(code).to_numpy()
    observed = table["mean_impact"].to_numpy()
    null_mean, null_sd, z, p = baseline.z_and_p(observed, null[codes])
    q = baseline.benjamini_hochberg(p)
    scores = [
        GroupScore(
            group=row.group, level=level, n_neurons=int(row.n_neurons), mean_direct=float(row.mean_direct),
            mean_impact=float(row.mean_impact), n_strong_hits=int(row.n_strong_hits),
            null_mean=float(null_mean[k]), null_sd=float(null_sd[k]), z_score=float(z[k]),
            p_value=float(p[k]), q_value=float(q[k]),
            above_chance=bool(q[k] < config.FDR_ALPHA and z[k] > 0),
            function_label=conn.function_label(row.group) if level in LABELLED_LEVELS else None,
        )
        for k, row in enumerate(table.itertuples(index=False))
    ]
    return sorted(scores, key=lambda g: -g.z_score)


def _top_neurons(conn: Connectome, prop: Propagation) -> list[NeuronImpact]:
    candidates = np.flatnonzero((prop.impact > 0) & ~prop.seed_mask)
    top = candidates[np.argsort(-prop.impact[candidates], kind="stable")[:TOP_NEURONS]]
    return [
        NeuronImpact(root_id=int(conn.root_ids[p]), cell_type=_label(conn, p, "cell_type"),
                     region=_label(conn, p, "region"), direct=float(prop.direct[p]), impact=float(prop.impact[p]),
                     per_hop=[float(h[p]) for h in prop.per_hop])
        for p in top
    ]


def _label(conn: Connectome, position: int, column: str) -> str | None:
    value = conn.neurons.iloc[position].get(column)
    return None if value is None or (isinstance(value, float) and np.isnan(value)) else str(value)


def clear_cache() -> None:
    _RESULTS.clear()
    _STATE.clear()


def get_result(run_id: str) -> SimulationResult:
    """Look up a cached run; KeyError if unknown."""
    return _RESULTS[run_id]


def get_subgraph(run_id: str) -> Subgraph:
    state = _STATE[run_id]
    if state.subgraph is None:
        state.subgraph = subgraph.neuron_subgraph(state.conn, state.prop, state.seed_positions,
                                                  config.SUBGRAPH_MAX_NODES, x0=state.x0)
    return state.subgraph


def get_sankey(run_id: str) -> list[SankeyLink]:
    state = _STATE[run_id]
    if state.sankey is None:
        req = _RESULTS[run_id].request
        state.sankey = subgraph.sankey_links(state.conn, state.seeds, req.mode, req.strength, req.hops, req.decay)
    return state.sankey


def compare(run_a: str, run_b: str, level: GroupLevel = GroupLevel.REGION) -> Comparison:
    return compare_mod.compare_runs(get_result(run_a), get_result(run_b), level)


def explain_neuron(run_id: str, root_id: int) -> dict:
    """Top paths from the seeds to this neuron, with weights, for the
    'why is this neuron hit?' panel and the agent."""
    state = _STATE[run_id]
    conn, prop = state.conn, state.prop
    target = int(conn.positions([root_id])[0])
    paths = subgraph.top_paths_with_strength(conn, state.seed_positions, target, k=3, hops=_RESULTS[run_id].request.hops)

    def name(p: int) -> str:
        return _label(conn, p, "cell_type") or str(conn.root_ids[p])

    return {
        "root_id": int(root_id),
        "cell_type": _label(conn, target, "cell_type"),
        "region": _label(conn, target, "region"),
        "is_seed": bool(prop.seed_mask[target]),
        "direct": float(prop.direct[target]),
        "impact": float(prop.impact[target]),
        "paths": [
            {"neurons": [name(p) for p in path], "root_ids": [int(conn.root_ids[p]) for p in path],
             "strength": strength}
            for path, strength in paths
        ],
    }
