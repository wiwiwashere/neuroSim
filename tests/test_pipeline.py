"""The whole pipeline on the synthetic brain: the design doc's sanity checks
(section 9) that need more than the toy graph."""

import numpy as np
import pytest

from neurosim.bio import evidence
from neurosim.engine import pipeline
from neurosim.engine.graph import load_connectome, set_connectome
from neurosim.engine.subgraph import sankey_links
from neurosim.engine.synthetic import synthetic_connectome
from neurosim.models import GroupLevel, PerturbationMode, SeedSet, SeedType, SimulationRequest

from engine_status import needs_engine


@pytest.fixture(autouse=True, scope="module")
def synthetic_brain():
    set_connectome(synthetic_connectome())
    pipeline.clear_cache()
    yield
    pipeline.clear_cache()
    set_connectome(None)


def custom_seeds(name: str, root_ids, cluster: str = "custom") -> SeedSet:
    seeds = evidence.validation_seeds()
    seed_type = SeedType(cell_type=name, cluster=cluster, match="exact", n_neurons=len(root_ids),
                         root_ids=[int(r) for r in root_ids], confidence=1.0, evidence=[])
    return seeds.model_copy(update={"human_gene": name, "seed_types": [seed_type]})


@needs_engine
def test_same_request_gives_identical_results():
    request = SimulationRequest(human_gene="PRKN")
    first = pipeline.run_simulation(request).model_dump_json()
    pipeline.clear_cache()
    assert pipeline.run_simulation(request).model_dump_json() == first


@needs_engine
def test_groups_are_sorted_by_z_and_seeds_are_not_reported():
    result = pipeline.run_simulation(SimulationRequest(human_gene="PRKN"))
    for scores in result.groups.values():
        z = [g.z_score for g in scores]
        assert z == sorted(z, reverse=True)
    seed_ids = set(result.seeds.root_ids)
    assert not seed_ids & {n.root_id for n in result.top_neurons}
    assert result.n_seed_neurons == len(seed_ids)


@needs_engine
def test_reduce_output_halves_impact_but_keeps_z_scores():
    full = pipeline.run_simulation(SimulationRequest(human_gene="PRKN"))
    half = pipeline.run_simulation(SimulationRequest(human_gene="PRKN", mode=PerturbationMode.REDUCE_OUTPUT,
                                                     strength=0.5))
    assert half.disruption_score == pytest.approx(0.5 * full.disruption_score)
    z_full = {g.group: g.z_score for g in full.groups[GroupLevel.REGION]}
    z_half = {g.group: g.z_score for g in half.groups[GroupLevel.REGION]}
    assert z_half == pytest.approx(z_full)


@needs_engine
def test_sankey_bands_add_up_to_the_total_impact():
    conn = load_connectome()
    prkn = evidence.resolve_seeds(SimulationRequest(human_gene="PRKN"))
    pam = evidence.validation_seeds()
    both = prkn.model_copy(update={"seed_types": prkn.seed_types + pam.seed_types})
    links = sankey_links(conn, both, PerturbationMode.KNOCKOUT, 1.0, 3, 0.5, min_share=0.0)
    assert {link.source for link in links} == {"PPL1", "PAM"}

    from neurosim.engine.perturb import initial_deficit
    from neurosim.engine.propagate import propagate

    seeds = conn.positions(both.root_ids)
    prop = propagate(conn.A, initial_deficit(conn.n, seeds, PerturbationMode.KNOCKOUT), 3, 0.5)
    assert sum(link.value for link in links) == pytest.approx(prop.impact[~prop.seed_mask].sum())


@needs_engine
def test_random_da_seeds_are_not_above_chance():
    conn = load_connectome()
    rng = np.random.default_rng(1)
    root_ids = conn.root_ids[rng.choice(conn.dopaminergic(), 20, replace=False)]
    result = pipeline.run_simulation(SimulationRequest(human_gene="RANDOM"), seeds=custom_seeds("RANDOM", root_ids))
    z = [g.z_score for g in result.groups[GroupLevel.REGION]]
    assert abs(np.median(z)) < 1.0
    assert not any(g.above_chance for g in result.groups[GroupLevel.SUPER_REGION])


def test_gene_without_matched_cell_types_raises_a_seed_error():
    with pytest.raises(evidence.SeedError):
        pipeline.run_simulation(SimulationRequest(human_gene="PINK1"))


@needs_engine
def test_drawing_endpoints_and_comparison_work_from_a_run_id():
    a = pipeline.run_simulation(SimulationRequest(human_gene="PRKN"))
    b = pipeline.run_simulation(SimulationRequest(human_gene="LRRK2"))
    assert pipeline.get_sankey(a.run_id)
    sub = pipeline.get_subgraph(a.run_id)
    assert 0 < len(sub.nodes) <= 200 and any(n.is_seed for n in sub.nodes)
    explained = pipeline.explain_neuron(a.run_id, a.top_neurons[0].root_id)
    assert explained["paths"] and explained["paths"][0]["root_ids"][0] in set(a.seeds.root_ids)
    comparison = pipeline.compare(a.run_id, b.run_id, GroupLevel.SUPER_REGION)
    assert comparison.spearman_rho == pytest.approx(1.0)  # same PPL1 seeds, only confidence differs
