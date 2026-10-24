"""Tools the agent may call (CS2). Each is a thin wrapper over engine/pipeline.py
or bio/evidence.py and returns JSON text. No tool computes anything itself,
which keeps the science in one deterministic place the agent cannot change.

Keep results small: the agent needs top groups and z-scores, not 139k neurons.
"""

from __future__ import annotations

from anthropic import beta_tool


@beta_tool
def list_diseases() -> str:
    """List the diseases neuroSim has evidence for."""
    raise NotImplementedError


@beta_tool
def get_gene_chain(human_gene: str, high_confidence_only: bool = False) -> str:
    """Get the mapping chain for a human disease gene: fly ortholog, published
    evidence of which dopamine neuron clusters are lost, matched connectome cell
    types, neuron counts and the confidence of every link.

    Args:
        human_gene: Human gene symbol, e.g. PINK1.
        high_confidence_only: Drop low-tier evidence and inferred cell-type matches.
    """
    raise NotImplementedError


@beta_tool
def run_simulation(
    human_gene: str,
    mode: str = "knockout",
    strength: float = 1.0,
    seed_cell_types: list[str] | None = None,
) -> str:
    """Run a perturbation experiment on the fly connectome and return the run id,
    disruption score, and the top brain regions and cell types with z-scores
    against random dopamine neurons.

    Args:
        human_gene: Human gene symbol, e.g. PINK1.
        mode: "knockout" or "reduce_output".
        strength: For reduce_output, the share of output lost, 0 to 1.
        seed_cell_types: Optional subset of seed cell types to perturb, e.g. ["PPL101"].
    """
    raise NotImplementedError


@beta_tool
def compare_runs(run_a: str, run_b: str, level: str = "region") -> str:
    """Compare two finished runs: rank correlation of their region or cell-type
    scores, regions above chance in both, and regions unique to each.

    Args:
        run_a: Run id from run_simulation.
        run_b: Run id from run_simulation.
        level: "region", "super_region", "cell_type" or "super_class".
    """
    raise NotImplementedError


@beta_tool
def explain_neuron(run_id: str, root_id: int) -> str:
    """Return the strongest connection paths from the seed neurons to one neuron,
    explaining why it scored high.

    Args:
        run_id: Run id from run_simulation.
        root_id: FlyWire root id of the neuron.
    """
    raise NotImplementedError


ALL_TOOLS = [list_diseases, get_gene_chain, run_simulation, compare_runs, explain_neuron]
