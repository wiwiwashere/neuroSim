"""Tools the agent may call (CS2). Each is a thin wrapper over engine/pipeline.py
or bio/evidence.py and returns JSON text. No tool computes anything itself,
which keeps the science in one deterministic place the agent cannot change.

Keep results small: the agent needs top groups and z-scores, not 139k neurons.

Gemini function calling needs two things per tool: the Python function
(TOOLS, which agent.py calls) and a JSON-schema declaration (TOOL_DECLARATIONS,
which is sent to the model). Keep the two in sync when you add a tool.
"""

from __future__ import annotations

import json

from neurosim import config
from neurosim.api import mocks
from neurosim.bio import custom, evidence, targets
from neurosim.engine import pipeline
from neurosim.models import GroupLevel, PerturbationMode, SeedSet, SimulationRequest, SimulationResult

# Sent with every result while the API serves mocks, so the agent says so.
_SAMPLE_NOTE = "Sample numbers: the engine isn't built yet, so these are fixed placeholder values, not real results."
TOP_GROUPS = 5
TOP_NEURONS = 5


def _dump(payload: dict) -> str:
    if config.USE_MOCKS:
        payload = {"note": _SAMPLE_NOTE, **payload}
    return json.dumps(payload, default=str)


def _seeds(human_gene: str, high_confidence_only: bool, disease: str | None = None) -> SeedSet:
    request = SimulationRequest(human_gene=human_gene, high_confidence_only=high_confidence_only, disease=disease or None)
    try:
        return mocks.mock_seeds(request) if config.USE_MOCKS else evidence.resolve_seeds(request)
    except evidence.SeedError as err:
        known = ", ".join(f"{g['human_gene']} ({d})" for d in evidence.list_diseases()
                          for g in evidence.list_genes(d) if g["simulatable"])
        raise ValueError(f"{err}. Genes that can be simulated: {known}.") from err


def _simulate(request: SimulationRequest) -> SimulationResult:
    return mocks.mock_result(request) if config.USE_MOCKS else pipeline.run_simulation(request)


def summarize_result(result: SimulationResult) -> dict:
    """The compact view of a run the agent sees (also used for the run summary)."""
    req = result.request
    return {
        "run_id": result.run_id,
        "request": {
            "human_gene": req.human_gene,
            "disease": result.seeds.disease,
            "user_supplied": result.seeds.user_supplied,
            "mode": req.mode.value,
            "strength": req.strength,
            "high_confidence_only": req.high_confidence_only,
            "seed_cell_types": req.seed_cell_types,
        },
        "seed_cell_types": [t.cell_type for t in result.seeds.seed_types],
        "n_seed_neurons": result.n_seed_neurons,
        "n_reached": result.n_reached,
        "disruption_score": result.disruption_score,
        "disruption_null_mean": result.disruption_null_mean,
        "disruption_z": result.disruption_z,
        "top_groups": {
            level.value: [
                {
                    "group": g.group,
                    "z_score": round(g.z_score, 2),
                    "q_value": g.q_value,
                    "above_chance": g.above_chance,
                    "n_neurons": g.n_neurons,
                    "function_label": g.function_label,
                }
                for g in groups[:TOP_GROUPS]
            ]
            for level, groups in result.groups.items()
        },
        "top_neurons": [
            {"root_id": n.root_id, "cell_type": n.cell_type, "region": n.region, "direct": n.direct, "impact": n.impact}
            for n in result.top_neurons[:TOP_NEURONS]
        ],
        "assumptions": result.assumptions,
    }


def list_diseases() -> str:
    """List the diseases neuroSim has evidence for, built in and user-added."""
    added = {d["id"]: d for d in custom.list_custom()}
    diseases = [
        {"id": d, "name": added[d]["name"] if d in added else d, "user_supplied": d in added,
         "genes": [g["human_gene"] for g in evidence.list_genes(d) if g["simulatable"]]}
        for d in evidence.list_diseases()
    ]
    # The table needs no engine, so no sample note from _dump.
    return json.dumps({"diseases": diseases, "note": "user_supplied diseases were added by the user and not reviewed "
                       "by Bio; say so when you report their results."})


def get_gene_chain(human_gene: str, high_confidence_only: bool = False, disease: str | None = None) -> str:
    """Fly ortholog, lost dopamine clusters, matched cell types, neuron counts, confidence."""
    seeds = _seeds(human_gene.upper(), high_confidence_only, disease)
    return _dump(
        {
            "human_gene": seeds.human_gene,
            "disease": seeds.disease,
            "user_supplied": seeds.user_supplied,
            "ortholog": seeds.ortholog.model_dump(),
            "seed_types": [
                {
                    "cell_type": t.cell_type,
                    "cluster": t.cluster,
                    "match": t.match,
                    "n_neurons": t.n_neurons,
                    "confidence": t.confidence,
                    "evidence": [
                        {"finding": e.finding, "citation": e.citation, "tier": e.tier, "model_type": e.model_type,
                         "verified_by_bio": e.verified_by_bio}
                        for e in t.evidence
                    ],
                }
                for t in seeds.seed_types
            ],
        }
    )


def get_direct_targets(human_gene: str, high_confidence_only: bool = False) -> str:
    """Cell types the gene's lost clusters synapse onto, with atlas expression where measured."""
    found = targets.direct_targets(human_gene.upper(), high_confidence_only)
    if found is None:
        raise ValueError(f"no evidence row names the dopamine clusters lost for {human_gene.upper()}, "
                         "so there are no direct targets to list")
    payload = found.model_dump(exclude={"targets"})
    payload["targets"] = [
        {"cell_type": t.cell_type, "synapses": t.synapses, "by_cluster": t.by_cluster, "n_neurons": t.n_neurons,
         "expression_tpm": t.expression.tpm if t.expression else "not measured",
         **({"atlas_match": t.expression.match} if t.expression else {})}
        for t in found.targets
    ]
    payload["note"] = ("Synapse counts from FlyWire connections, not a simulation. Expression is bulk RNA-seq "
                       "context; 'not measured' does not mean not expressed.")
    # Real data in mock mode too, so no sample note from _dump.
    return json.dumps(payload, default=str)


def run_simulation(
    human_gene: str,
    mode: str = "knockout",
    strength: float = 1.0,
    seed_cell_types: list[str] | None = None,
    disease: str | None = None,
) -> str:
    """Run a perturbation; return run id, disruption score and top groups with z-scores."""
    human_gene = human_gene.upper()
    seeds = _seeds(human_gene, False, disease)
    if seed_cell_types:
        available = {t.cell_type for t in seeds.seed_types}
        missing = [t for t in seed_cell_types if t not in available]
        if missing:
            raise ValueError(f"{', '.join(missing)} is not a seed type for {human_gene}. Its seed types: {', '.join(sorted(available))}.")
    request = SimulationRequest(
        human_gene=human_gene,
        mode=PerturbationMode(mode),
        strength=1.0 if mode == "knockout" else strength,
        seed_cell_types=seed_cell_types or None,
        disease=disease or None,
    )
    return _dump(summarize_result(_simulate(request)))


def compare_runs(run_a: str, run_b: str, level: str = "region") -> str:
    """Rank correlation of two runs, groups above chance in both, groups unique to each."""
    cmp = mocks.mock_comparison(run_a, run_b) if config.USE_MOCKS else pipeline.compare(run_a, run_b, GroupLevel(level))
    return _dump(cmp.model_dump(mode="json"))


def explain_neuron(run_id: str, root_id: int) -> str:
    """Strongest connection paths from the seed neurons to one neuron."""
    if config.USE_MOCKS:
        return _dump({"root_id": root_id, "paths": [{"neurons": ["PPL101", "MBON01"], "strength": 0.41}]})
    return _dump(pipeline.explain_neuron(run_id, int(root_id)))


TOOLS = {
    "list_diseases": list_diseases,
    "get_gene_chain": get_gene_chain,
    "get_direct_targets": get_direct_targets,
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
_DISEASE = {"type": "string", "description": "Disease id from list_diseases. Only needed for a user-added disease, "
            "or when a gene has rows for more than one disease."}

TOOL_DECLARATIONS = [
    _fn("list_diseases", "List the diseases neuroSim has evidence for (built in and user-added) with their genes.", {}, []),
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
            "disease": _DISEASE,
        },
        ["human_gene"],
    ),
    _fn(
        "get_direct_targets",
        "List the connectome cell types that the gene's lost dopamine clusters synapse onto "
        "directly (one synapse away), with synapse counts per cluster and, where the "
        "expression atlas measured them, the fly ortholog's expression in those targets. "
        "Real FlyWire connectivity, available even when simulations return sample numbers.",
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
            "disease": _DISEASE,
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
