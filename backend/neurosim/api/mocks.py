"""Fixed sample payloads (CS2) so the frontend can be built before the engine works.

Every number here is FAKE, except the seeds (see mock_seeds). They have the right shape and roughly the right
size so layouts and charts can be built. Delete this file's use once
pipeline.run_simulation works (set NEUROSIM_MOCKS=0).
"""

from __future__ import annotations

from neurosim.bio import evidence, expression
from neurosim.engine import graph
from neurosim.models import (
    Comparison,
    EvidenceRow,
    GraphEdge,
    GraphNode,
    GroupLevel,
    GroupScore,
    NeuronImpact,
    SankeyLink,
    SeedSet,
    SeedType,
    SimulationRequest,
    SimulationResult,
    Subgraph,
)

_EVIDENCE = EvidenceRow(
    disease="parkinsons", human_gene="PRKN", fly_gene="park", model_type="mutant",
    clusters=["PPL1"], finding="FAKE: parkin mutants lose PPL1 dopamine neurons.",
    citation="Whitworth et al. 2005, PNAS", url="https://flybase.org/reports/FBrf0188281",
    tier="medium",
)


def mock_seeds(request: SimulationRequest | str = "PRKN") -> SeedSet:
    """Seeds for a mock run. Seed resolution doesn't need the engine, so when
    the connectome is on disk these are the real ones from the evidence table
    (rows approved from paper uploads included, SeedError for a gene that
    can't be simulated). Without it, the table's ortholog and two fake PPL1 types."""
    if isinstance(request, str):
        request = SimulationRequest(human_gene=request)
    if graph.connectome_available():
        return evidence.resolve_seeds(request)
    gene = request.human_gene
    ortholog = evidence.find_ortholog(gene)   # SeedError for a gene the table doesn't know
    if not ortholog.fly_genes:
        raise evidence.SeedError(f"{gene} has no fly ortholog, so it cannot be simulated in the fly connectome")
    seeds = SeedSet(
        disease="parkinsons",
        human_gene=gene,
        ortholog=ortholog,
        seed_types=[
            SeedType(cell_type="PPL101", cluster="PPL1", match="exact", n_neurons=2,
                     root_ids=[720575940000000001, 720575940000000002], confidence=0.63, evidence=[_EVIDENCE]),
            SeedType(cell_type="PPL102", cluster="PPL1", match="exact", n_neurons=2,
                     root_ids=[720575940000000003, 720575940000000004], confidence=0.63, evidence=[_EVIDENCE]),
        ],
    )
    if request.seed_cell_types:
        seeds.seed_types = [t for t in seeds.seed_types if t.cell_type in request.seed_cell_types]
    return expression.annotate(seeds)


def _group(name: str, z: float, label: str) -> GroupScore:
    return GroupScore(group=name, level=GroupLevel.SUPER_REGION, n_neurons=1200, mean_direct=0.02 * z,
                      mean_impact=0.03 * z, n_strong_hits=int(10 * z), null_mean=0.01, null_sd=0.005,
                      z_score=z, p_value=0.005 if z > 2 else 0.4, q_value=0.02 if z > 2 else 0.6,
                      above_chance=z > 2, function_label=label)


# Runs made this session, so GET /runs/{id} returns what was asked for.
_RUNS: dict[str, SimulationResult] = {}


def _mock_run_id(request: SimulationRequest) -> str:
    # Deterministic from the request, like pipeline.run_id_for.
    parts = ["mock", request.human_gene.lower(), request.mode.value]
    if request.mode.value == "reduce_output":
        parts.append(f"{round(request.strength * 100)}")
    if request.high_confidence_only:
        parts.append("hc")
    if request.seed_cell_types:
        parts.append("+".join(sorted(request.seed_cell_types)))
    return "-".join(parts)


def mock_result(request: SimulationRequest | None = None) -> SimulationResult:
    request = request or SimulationRequest(human_gene="PRKN")
    seeds = mock_seeds(request)
    result = SimulationResult(
        run_id=_mock_run_id(request),
        request=request,
        seeds=seeds,
        n_seed_neurons=len(seeds.root_ids),
        n_reached=5321,
        disruption_score=0.004,
        disruption_null_mean=0.002,
        disruption_z=3.1,
        groups={
            GroupLevel.SUPER_REGION: [
                _group("mushroom body", 6.2, "learning and memory"),
                _group("lateral horn", 2.4, "innate odour responses"),
                _group("central complex", 1.1, "navigation and walking"),
                _group("optic lobe", -0.3, "vision"),
            ],
        },
        top_neurons=[
            NeuronImpact(root_id=720575940000000100, cell_type="MBON01", region="MB_ML_R",
                         direct=0.41, impact=0.52, per_hop=[0.41, 0.18, 0.04]),
        ],
        assumptions={"synapse_threshold": 5, "hops": 3, "decay": 0.5, "null": "random DA neurons x200"},
    )
    _RUNS[result.run_id] = result
    return result


def mock_run(run_id: str) -> SimulationResult:
    return _RUNS.get(run_id) or mock_result()


def mock_subgraph() -> Subgraph:
    return Subgraph(
        nodes=[
            GraphNode(id="s1", label="PPL101", group="MB_ML_R", is_seed=True, impact=1.0, x=0, y=0),
            GraphNode(id="n1", label="MBON01", group="MB_ML_R", is_seed=False, impact=0.52, x=120, y=0),
            GraphNode(id="n2", label="KCg-m", group="MB_CA_R", is_seed=False, impact=0.21, x=120, y=90),
        ],
        edges=[
            GraphEdge(source="s1", target="n1", weight=0.41, synapses=58, lost=0.41),
            GraphEdge(source="s1", target="n2", weight=0.12, synapses=17, lost=0.12),
        ],
    )


def mock_sankey() -> list[SankeyLink]:
    return [
        SankeyLink(source="PPL1", target="mushroom body", value=12.0),
        SankeyLink(source="PPL1", target="lateral horn", value=3.5),
        SankeyLink(source="PPL1", target="central complex", value=1.2),
    ]


def mock_comparison(run_a: str = "mock-pink1-knockout", run_b: str = "mock-prkn-knockout") -> Comparison:
    gene_a = _RUNS[run_a].request.human_gene if run_a in _RUNS else "PINK1"
    gene_b = _RUNS[run_b].request.human_gene if run_b in _RUNS else "PRKN"
    return Comparison(run_a=run_a, run_b=run_b, level=GroupLevel.SUPER_REGION,
                      spearman_rho=0.41, shared_top=["mushroom body"], only_a=["central complex"],
                      only_b=["lateral horn"],
                      summary=f"FAKE: {gene_a} and {gene_b} share 1 of their top regions (rank correlation 0.41).")
