"""Built-in validation: does the engine recover a known Parkinson's-model
result? (CS1, docs/ENGINE_DESIGN.md, section 9.)

Riemensperger et al. 2013: alpha-synuclein in the PAM neurons that innervate
the mushroom body beta-prime lobe weakens their input there, and that lobe is
needed for climbing. So, seeding those PAM neurons, the engine should find:

    1. the beta-prime output neurons (MBONs) hit far above chance against the
       headline null (random DA neurons of the same number), and
    2. the mushroom body above chance against random neurons of any type.

Why the MBONs and not a region: FlyWire's neuropil labels do not split the
medial lobe into beta, beta-prime and gamma compartments, and every MBON type
has fewer neurons than config.MIN_GROUP_SIZE, so neither shows up in the
ranked lists. The check therefore treats the beta-prime MBONs as one
pre-registered target set and scores it with the same null machinery.

Run:  python -m neurosim.engine.validation             (real data if present)
      python -m neurosim.engine.validation --synthetic (the made-up test brain)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import numpy as np

from neurosim import config
from neurosim.bio import evidence
from neurosim.engine import baseline, pipeline, vulnerability
from neurosim.engine.graph import Connectome, load_connectome, processed_data_available, set_connectome
from neurosim.models import GroupLevel, PerturbationMode, SimulationRequest, SimulationResult

# MBON types with a dendrite in a beta-prime compartment (hemibrain/FlyWire
# naming, Li et al. 2020): g5b'2a, b2b'2a, b'2mp, b'2mp_bilateral, g3b'1, b'1.
# Bio: confirm against the FlyWire cell type table before the demo.
BETA_PRIME_MBON_TYPES = ["MBON01", "MBON02", "MBON03", "MBON04", "MBON09", "MBON10"]
SYNTHETIC_BETA_PRIME_MBON_TYPES = ["MBON_b'1", "MBON_b'2"]
MUSHROOM_BODY = "mushroom body"


@dataclass
class TargetScore:
    name: str
    n_neurons: int
    observed: float
    null_mean: float
    z: float
    p: float

    @property
    def above_chance(self) -> bool:
        return self.z > 0 and self.p < config.FDR_ALPHA

    def line(self) -> str:
        verdict = "ABOVE CHANCE" if self.above_chance else "not above chance"
        return (f"{self.name}: mean impact {self.observed:.4f} vs null {self.null_mean:.4f} "
                f"(n={self.n_neurons}, z={self.z:.2f}, p={self.p:.3f}) -> {verdict}")


@dataclass
class ValidationReport:
    connectome: str
    seed_types: list[str]
    n_seeds: int
    mbons_vs_da: TargetScore
    mbons_vs_any: TargetScore
    mb_vs_any: TargetScore
    mb_vs_da: TargetScore
    mbon_percentile: float
    top_cell_types: list[str]

    @property
    def passed(self) -> bool:
        return self.mbons_vs_da.above_chance and self.mb_vs_any.above_chance

    def text(self) -> str:
        lines = [
            f"PAM -> mushroom body validation on {self.connectome}",
            f"Seeds: {self.n_seeds} neurons of {', '.join(self.seed_types)}",
            "",
            "Headline null (random DA neurons):",
            "  " + self.mbons_vs_da.line(),
            "  " + self.mb_vs_da.line(),
            "Weaker null (random neurons of any type):",
            "  " + self.mbons_vs_any.line(),
            "  " + self.mb_vs_any.line(),
            "",
            f"Beta-prime MBONs sit at the {self.mbon_percentile:.1f}th percentile of all neurons by impact.",
            f"Most-hit cell types: {', '.join(self.top_cell_types)}",
            "",
            "RESULT: " + ("PASS, the engine recovers the known PAM -> beta-prime result."
                          if self.passed else "FAIL, find out why before the demo (cell types? region labels?)."),
        ]
        return "\n".join(lines)


def beta_prime_mbons(conn: Connectome) -> np.ndarray:
    cell_type = conn.neurons["cell_type"].astype("string")
    for names in (BETA_PRIME_MBON_TYPES, SYNTHETIC_BETA_PRIME_MBON_TYPES):
        hits = np.flatnonzero(cell_type.isin(names).fillna(False).to_numpy())
        if hits.size:
            return hits
    raise ValueError("no beta-prime MBON cell types found in the connectome")


def _target_score(name: str, conn: Connectome, members: np.ndarray, result: SimulationResult,
                  seed_positions: np.ndarray, pool: np.ndarray) -> TargetScore:
    req = result.request
    codes = np.ones(conn.n, dtype=np.int64)
    codes[members] = 0
    state_impact = pipeline._STATE[result.run_id].prop.impact
    keep = np.setdiff1d(members, seed_positions)
    observed = float(state_impact[keep].mean())
    null, _ = baseline.null_distributions(conn, len(seed_positions), req.mode, req.strength, req.hops, req.decay,
                                          {"target": (codes, 2)}, pool)
    null_mean, _, z, p = baseline.z_and_p(np.array([observed]), null["target"][:1])
    return TargetScore(name, len(keep), observed, float(null_mean[0]), float(z[0]), float(p[0]))


def run_validation() -> ValidationReport:
    conn = load_connectome()
    seeds = evidence.validation_seeds()
    request = SimulationRequest(human_gene=seeds.human_gene, mode=PerturbationMode.KNOCKOUT,
                                seed_cell_types=[t.cell_type for t in seeds.seed_types])
    result = pipeline.run_simulation(request, seeds=seeds)
    seed_positions = np.unique(conn.positions(seeds.root_ids))
    impact = pipeline._STATE[result.run_id].prop.impact

    mbons = beta_prime_mbons(conn)
    codes, names = vulnerability.group_codes(conn.neurons, GroupLevel.SUPER_REGION)
    mb = np.flatnonzero(codes == names.index(MUSHROOM_BODY))
    da_pool, any_pool = conn.dopaminergic(), np.arange(conn.n)

    healthy = np.setdiff1d(np.arange(conn.n), seed_positions)
    ranks = impact[healthy].argsort().argsort()
    rank_of = dict(zip(healthy, ranks))
    mbon_rank = np.mean([rank_of[m] for m in np.setdiff1d(mbons, seed_positions)])

    return ValidationReport(
        connectome=conn.source,
        seed_types=[t.cell_type for t in seeds.seed_types],
        n_seeds=len(seed_positions),
        mbons_vs_da=_target_score("beta-prime MBONs", conn, mbons, result, seed_positions, da_pool),
        mbons_vs_any=_target_score("beta-prime MBONs", conn, mbons, result, seed_positions, any_pool),
        mb_vs_any=_target_score(MUSHROOM_BODY, conn, mb, result, seed_positions, any_pool),
        mb_vs_da=_target_score(MUSHROOM_BODY, conn, mb, result, seed_positions, da_pool),
        mbon_percentile=100.0 * mbon_rank / max(len(healthy) - 1, 1),
        top_cell_types=list(dict.fromkeys(n.cell_type for n in result.top_neurons if n.cell_type))[:8],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--synthetic", action="store_true", help="use the made-up test brain")
    args = parser.parse_args(argv)
    if args.synthetic or not processed_data_available():
        if not args.synthetic:
            print("data/processed not found, falling back to the synthetic test brain\n")
        from neurosim.engine.synthetic import synthetic_connectome

        set_connectome(synthetic_connectome())
    report = run_validation()
    print(report.text())
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
