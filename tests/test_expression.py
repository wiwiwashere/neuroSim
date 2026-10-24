"""Kait's expression atlas as an annotation on the seeds: PAM only, never a veto."""

import pytest

from neurosim import config
from neurosim.bio import evidence, expression
from neurosim.engine.graph import set_connectome
from neurosim.engine.synthetic import synthetic_connectome
from neurosim.models import SeedSet, SeedType, SimulationRequest


@pytest.fixture(autouse=True, scope="module")
def synthetic_brain():
    set_connectome(synthetic_connectome())
    yield
    set_connectome(None)


def test_atlas_covers_pam_only_and_maps_its_lines_to_flywire_types():
    pink1 = expression.gene_expression("PINK1")
    assert pink1.fly_genes == ["Pink1"] and pink1.clusters_measured == ["PAM"]
    by_type = {e.cell_type: e for e in pink1.cell_types}
    assert all(t.startswith("PAM") for t in by_type)
    # PAM08 has its own driver line (PAM_4), so the pooled lines PAM_2 and PAM_6 don't count.
    assert by_type["PAM08"].match == "inferred" and by_type["PAM08"].atlas_labels == ["dopaminergic PAM neuron 4"]
    assert by_type["PAM06"].match == "coarse"


def test_spellings_and_missing_orthologs():
    assert expression.gene_expression("PARK7").fly_genes == ["dj-1beta", "DJ-1alpha"]
    rab = expression.gene_expression("RAB39B")
    assert rab.fly_genes == ["Rab39"] and rab.missing_fly_genes == ["RabX4"]
    assert expression.gene_expression("SNCA") is None


def test_expression_never_changes_seeds_or_confidence(monkeypatch):
    request = SimulationRequest(human_gene="PRKN")
    with_atlas = evidence.resolve_seeds(request)
    monkeypatch.setattr(config, "EXPRESSION_PATH", config.ROOT / "data" / "no-such-table.csv")
    without = evidence.resolve_seeds(request)
    assert without.expression is None and with_atlas.expression is not None
    assert [(t.cell_type, t.confidence, t.root_ids) for t in with_atlas.seed_types] == \
           [(t.cell_type, t.confidence, t.root_ids) for t in without.seed_types]
    # PRKN seeds PPL1, which the atlas never profiled: not measured, not zero.
    assert all(t.expression is None for t in with_atlas.seed_types)


def test_pam_seed_types_carry_their_values():
    seed = SeedType(cell_type="PAM08", cluster="PAM", match="exact", n_neurons=1, root_ids=[1],
                    confidence=0.5, evidence=[])
    seeds = expression.annotate(SeedSet(disease="parkinsons", human_gene="PRKN",
                                        ortholog=evidence.find_ortholog("PRKN"), seed_types=[seed]))
    assert seeds.seed_types[0].expression.tpm == {"park": 0.7}
    assert seeds.seed_types[0].confidence == 0.5
