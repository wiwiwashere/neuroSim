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

from neurosim.models import SankeyLink, Subgraph


def sankey_links(conn, seeds, mode, strength: float, hops: int, decay: float) -> list[SankeyLink]:
    """One propagation per seed cluster, aggregate impact by super region.
    Drop links below 1% of the total so the diagram stays readable."""
    raise NotImplementedError


def neuron_subgraph(conn, prop, seed_positions, max_nodes: int) -> Subgraph:
    """Pick nodes (all seeds if they fit, else the seeds with most downstream
    impact; then top neurons by impact), collect edges among them, compute a
    layout with networkx (e.g. spring_layout with a fixed seed, positions
    grouped by region), and fill the Subgraph contract."""
    raise NotImplementedError


def top_paths(conn, prop, seed_positions, target_position: int, k: int = 3) -> list[list[int]]:
    """The k strongest seed -> ... -> target paths, path strength = product of
    A weights along it, up to `hops` steps. Explains WHY a neuron scored high.
    Search backwards from the target over in-edges; the graph is small at this depth."""
    raise NotImplementedError
