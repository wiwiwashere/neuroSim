"""Seed resolution against the real evidence table and the synthetic brain."""

import pytest

from neurosim.bio import evidence
from neurosim.engine.graph import set_connectome
from neurosim.engine.synthetic import synthetic_connectome
from neurosim.models import SimulationRequest


@pytest.fixture(autouse=True, scope="module")
def synthetic_brain():
    set_connectome(synthetic_connectome())
    yield
    set_connectome(None)


def test_every_evidence_row_loads_with_a_citation():
    rows = evidence.load_evidence()["evidence"]
    assert rows and all(row.citation for row in rows)


def test_gene_without_ortholog_is_listed_but_not_simulatable():
    genes = {g["human_gene"]: g for g in evidence.list_genes("parkinsons")}
    assert genes["SNCA"]["simulatable"] is False
    with pytest.raises(evidence.SeedError, match="no fly ortholog"):
        evidence.resolve_seeds(SimulationRequest(human_gene="SNCA"))


def test_validation_row_is_never_a_gene_seed():
    assert all(not row.finding.startswith("VALIDATION") for row in evidence.evidence_for("SNCA"))


def test_seeds_resolve_to_connectome_root_ids_and_respect_filters():
    seeds = evidence.resolve_seeds(SimulationRequest(human_gene="PRKN"))
    assert {t.cluster for t in seeds.seed_types} == {"PPL1"}
    assert len(seeds.root_ids) == sum(t.n_neurons for t in seeds.seed_types) > 0
    only = evidence.resolve_seeds(SimulationRequest(human_gene="PRKN", seed_cell_types=["PPL101"]))
    assert [t.cell_type for t in only.seed_types] == ["PPL101"]
    with pytest.raises(evidence.SeedError):
        evidence.resolve_seeds(SimulationRequest(human_gene="PRKN", seed_cell_types=["PAM01"]))


def test_validation_seeds_are_beta_prime_pam_types():
    seeds = evidence.validation_seeds()
    assert {t.cell_type for t in seeds.seed_types} <= set(evidence.VALIDATION_PAM_TYPES)
    assert all(t.cluster == "PAM" for t in seeds.seed_types)
