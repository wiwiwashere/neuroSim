"""Tools the agent may call (CS2). Each is a thin wrapper over engine/pipeline.py
or bio/evidence.py and returns JSON text. No tool computes anything itself,
which keeps the science in one deterministic place the agent cannot change.

Keep results small: the agent needs top groups and z-scores, not 139k neurons.

Gemini function calling needs two things per tool: the Python function
(TOOLS, which agent.py calls) and a JSON-schema declaration (TOOL_DECLARATIONS,
which is sent to the model). Keep the two in sync when you add a tool.
"""

from __future__ import annotations


def list_diseases() -> str:
    """List the diseases neuroSim has evidence for."""
    raise NotImplementedError


def get_gene_chain(human_gene: str, high_confidence_only: bool = False) -> str:
    """Fly ortholog, lost dopamine clusters, matched cell types, neuron counts, confidence."""
    raise NotImplementedError


def run_simulation(
    human_gene: str,
    mode: str = "knockout",
    strength: float = 1.0,
    seed_cell_types: list[str] | None = None,
) -> str:
    """Run a perturbation; return run id, disruption score and top groups with z-scores."""
    raise NotImplementedError


def compare_runs(run_a: str, run_b: str, level: str = "region") -> str:
    """Rank correlation of two runs, groups above chance in both, groups unique to each."""
    raise NotImplementedError


def explain_neuron(run_id: str, root_id: int) -> str:
    """Strongest connection paths from the seed neurons to one neuron."""
    raise NotImplementedError


TOOLS = {
    "list_diseases": list_diseases,
    "get_gene_chain": get_gene_chain,
    "run_simulation": run_simulation,
    "compare_runs": compare_runs,
    "explain_neuron": explain_neuron,
}


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


_GENE = {"type": "string", "description": "Human gene symbol, e.g. PINK1."}
_RUN = {"type": "string", "description": "Run id from run_simulation."}

TOOL_DECLARATIONS = [
    _fn("list_diseases", "List the diseases neuroSim has evidence for.", {}, []),
    _fn(
        "get_gene_chain",
        "Get the mapping chain for a human disease gene: fly ortholog, published evidence "
        "of which dopamine neuron clusters are lost, matched connectome cell types, neuron "
        "counts and the confidence of every link.",
        {
            "human_gene": _GENE,
            "high_confidence_only": {
                "type": "boolean",
                "description": "Drop low-tier evidence and inferred cell-type matches.",
            },
        },
        ["human_gene"],
    ),
    _fn(
        "run_simulation",
        "Run a perturbation experiment on the fly connectome and return the run id, "
        "disruption score, and the top brain regions and cell types with z-scores against "
        "random dopamine neurons.",
        {
            "human_gene": _GENE,
            "mode": {"type": "string", "enum": ["knockout", "reduce_output"]},
            "strength": {
                "type": "number",
                "description": "For reduce_output, the share of output lost, 0 to 1.",
            },
            "seed_cell_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": 'Optional subset of seed cell types to perturb, e.g. ["PPL101"].',
            },
        },
        ["human_gene"],
    ),
    _fn(
        "compare_runs",
        "Compare two finished runs: rank correlation of their scores, groups above chance "
        "in both, and groups unique to each.",
        {
            "run_a": _RUN,
            "run_b": _RUN,
            "level": {"type": "string", "enum": ["region", "super_region", "cell_type", "super_class"]},
        },
        ["run_a", "run_b"],
    ),
    _fn(
        "explain_neuron",
        "Return the strongest connection paths from the seed neurons to one neuron, "
        "explaining why it scored high.",
        {
            "run_id": _RUN,
            "root_id": {"type": "integer", "description": "FlyWire root id of the neuron."},
        },
        ["run_id", "root_id"],
    ),
]
