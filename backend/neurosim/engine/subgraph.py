"""Small graphs for drawing (CS1 produces, CS2 draws). See docs/ENGINE_DESIGN.md, section 8.

The whole-brain computation never touches NetworkX. Only these small views do.

Two views:

1. Sankey (the hero visual): seed cluster -> super region, link value =
   summed impact in that region attributable to that cluster. Attribution:
   run propagation once per seed cluster (they are linear, so the per-cluster
   impacts add up exactly to the total). Cheap: a handful of clusters.

2. Neuron subgraph (the drill-down): seeds + the top-N neurons by impact,
   capped at config.SUBGRAPH_MAX_NODES, with the thresholded edges among them.
   Edges carry `lost` = edge weight x deficit of its source, so the frontend
   can fade exactly the drive that disappears.

Layout is computed ONCE on the healthy subgraph and reused for the perturbed
view, so the only thing that changes between before and after is colour and
edge strength. Group nodes by region (compound nodes in Cytoscape).
"""

from __future__ import annotations

import networkx as nx
import numpy as np

from neurosim.engine.perturb import initial_deficit
from neurosim.engine.propagate import propagate
from neurosim.engine.vulnerability import UNLABELLED
from neurosim.models import GraphEdge, GraphNode, SankeyLink, Subgraph

# Partial paths kept per step in top_paths. The real brain has neurons with
# thousands of inputs, so an exhaustive 3-step search is out; a beam this wide
# keeps every path that could plausibly be in the top k.
PATH_BEAM = 500
LAYOUT_SIZE = 1000.0


def sankey_links(conn, seeds, mode, strength: float, hops: int, decay: float) -> list[SankeyLink]:
    """One propagation per seed cluster, aggregate impact by super region.
    Drop links below 1% of the total so the diagram stays readable."""
    all_seeds = conn.positions(seeds.root_ids)
    healthy = np.ones(conn.n, dtype=bool)
    healthy[all_seeds] = False
    super_region = conn.neurons["super_region"].astype("object").where(conn.neurons["super_region"].notna(), UNLABELLED)
    clusters: dict[str, list[int]] = {}
    for seed_type in seeds.seed_types:
        clusters.setdefault(seed_type.cluster, []).extend(seed_type.root_ids)
    totals: dict[tuple[str, str], float] = {}
    for cluster, root_ids in clusters.items():
        x0 = initial_deficit(conn.n, conn.positions(root_ids), mode, strength)
        impact = propagate(conn.A, x0, hops, decay).impact
        by_region = (
            super_region[healthy].to_frame("target").assign(value=impact[healthy]).groupby("target")["value"].sum()
        )
        for target, value in by_region.items():
            totals[(cluster, target)] = totals.get((cluster, target), 0.0) + float(value)
    grand_total = sum(totals.values())
    links = [SankeyLink(source=c, target=t, value=v) for (c, t), v in totals.items()
             if grand_total > 0 and v >= 0.01 * grand_total]
    return sorted(links, key=lambda link: -link.value)


def neuron_subgraph(conn, prop, seed_positions, max_nodes: int, x0: np.ndarray | None = None) -> Subgraph:
    """Pick nodes (all seeds if they fit, else the seeds with most downstream
    impact; then top neurons by impact), collect edges among them, compute a
    layout with networkx (e.g. spring_layout with a fixed seed, positions
    grouped by region), and fill the Subgraph contract.

    Edge `lost` = input fraction x the source's deficit: x0 for a seed, its
    direct hit (h1, what it passes on at the next hop) for anything else.
    """
    seed_positions = np.asarray(seed_positions, dtype=np.int64)
    if x0 is None:
        x0 = prop.seed_mask.astype(float)
    reach = np.asarray(conn.A[:, seed_positions].sum(axis=0)).ravel()
    seed_cap = max(1, max_nodes // 2)
    seeds = seed_positions[np.argsort(-reach, kind="stable")[:seed_cap]]
    candidates = np.flatnonzero((prop.impact > 0) & ~prop.seed_mask)
    ranked = candidates[np.argsort(-prop.impact[candidates], kind="stable")]
    nodes = np.concatenate([seeds, ranked[: max_nodes - len(seeds)]])
    is_seed = set(seeds.tolist())

    sub_w = conn.W[nodes][:, nodes].tocoo()
    deficit = np.where(prop.seed_mask, x0, prop.direct)
    edges = []
    for a, b, syn in zip(sub_w.row, sub_w.col, sub_w.data):
        i, j = nodes[a], nodes[b]
        weight = float(conn.A[j, i])
        edges.append(GraphEdge(source=str(conn.root_ids[i]), target=str(conn.root_ids[j]), weight=weight,
                               synapses=int(syn), lost=weight * float(deficit[i])))

    positions = _layout(conn, nodes, sub_w)
    graph_nodes = []
    for p in nodes:
        row = conn.neurons.iloc[p]
        cell_type, region = row.get("cell_type"), row.get("region")
        x, y = positions[p]
        graph_nodes.append(GraphNode(
            id=str(conn.root_ids[p]),
            label=str(cell_type) if _present(cell_type) else str(conn.root_ids[p]),
            group=str(region) if _present(region) else UNLABELLED,
            is_seed=p in is_seed,
            impact=float(x0[p]) if p in is_seed else float(prop.impact[p]),
            x=x, y=y,
        ))
    return Subgraph(nodes=graph_nodes, edges=edges)


def _present(value) -> bool:
    return value is not None and not (isinstance(value, float) and np.isnan(value)) and str(value) != ""


def _layout(conn, nodes: np.ndarray, sub_w) -> dict[int, tuple[float, float]]:
    """Spring layout on the healthy subgraph, started from region clusters on a
    circle so neurons of one region sit together. Depends only on wiring, never
    on impact, so the healthy and perturbed views line up."""
    regions = [conn.neurons.iloc[p].get("region") for p in nodes]
    regions = [str(r) if _present(r) else UNLABELLED for r in regions]
    names = sorted(set(regions))
    angle = {name: 2 * np.pi * k / len(names) for k, name in enumerate(names)}
    rng = np.random.default_rng(0)
    start = {int(p): np.array([np.cos(angle[r]), np.sin(angle[r])]) + rng.normal(0, 0.15, 2)
             for p, r in zip(nodes, regions)}
    G = nx.Graph()
    G.add_nodes_from(int(p) for p in nodes)
    G.add_weighted_edges_from((int(nodes[a]), int(nodes[b]), float(w)) for a, b, w in zip(sub_w.row, sub_w.col, sub_w.data))
    pos = nx.spring_layout(G, pos=start, seed=0, iterations=50, weight=None, k=1.5 / max(np.sqrt(len(nodes)), 1))
    xy = np.array(list(pos.values()))
    lo, span = xy.min(axis=0), np.ptp(xy, axis=0)
    span[span == 0] = 1.0
    return {p: tuple(float(v) for v in (np.array(c) - lo) / span * LAYOUT_SIZE) for p, c in pos.items()}


def top_paths(conn, prop, seed_positions, target_position: int, k: int = 3, hops: int = 3) -> list[list[int]]:
    """The k strongest seed -> ... -> target paths, path strength = product of
    A weights along it, up to `hops` steps. Explains WHY a neuron scored high.
    Search backwards from the target over in-edges; the graph is small at this depth."""
    return [path for path, _ in top_paths_with_strength(conn, seed_positions, target_position, k, hops)]


def top_paths_with_strength(conn, seed_positions, target_position: int, k: int = 3,
                            hops: int = 3) -> list[tuple[list[int], float]]:
    """top_paths with each path's strength. Paths run seed first, target last."""
    seeds = set(np.asarray(seed_positions).tolist())
    A = conn.A
    found: list[tuple[list[int], float]] = []
    frontier: list[tuple[list[int], float]] = [([int(target_position)], 1.0)]
    for _ in range(hops):
        extended = []
        for path, strength in frontier:
            head = path[0]
            row = A.getrow(head)
            for src, w in zip(row.indices, row.data):
                src = int(src)
                if src in path:
                    continue
                candidate = ([src] + path, strength * float(w))
                (found if src in seeds else extended).append(candidate)
        frontier = sorted(extended, key=lambda item: -item[1])[:PATH_BEAM]
    return sorted(found, key=lambda item: -item[1])[:k]
