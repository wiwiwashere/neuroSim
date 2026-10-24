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

from neurosim.models import Comparison, GroupLevel, SankeyLink, SimulationRequest, SimulationResult, Subgraph

_RESULTS: dict[str, SimulationResult] = {}


def run_id_for(request: SimulationRequest) -> str:
    """Deterministic short hash of the request and the relevant config values."""
    raise NotImplementedError


def run_simulation(request: SimulationRequest) -> SimulationResult:
    raise NotImplementedError


def get_result(run_id: str) -> SimulationResult:
    """Look up a cached run; KeyError if unknown."""
    raise NotImplementedError


def get_subgraph(run_id: str) -> Subgraph:
    raise NotImplementedError


def get_sankey(run_id: str) -> list[SankeyLink]:
    raise NotImplementedError


def compare(run_a: str, run_b: str, level: GroupLevel = GroupLevel.REGION) -> Comparison:
    raise NotImplementedError


def explain_neuron(run_id: str, root_id: int) -> dict:
    """Top paths from the seeds to this neuron, with weights, for the
    'why is this neuron hit?' panel and the agent."""
    raise NotImplementedError
