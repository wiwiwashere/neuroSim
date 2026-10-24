"""Random-seed baseline (CS1). See docs/ENGINE_DESIGN.md, section 7.

The question every result must answer: "is this more than you'd get from
any random set of neurons like these?"

Null model: draw config.N_RANDOM_DRAWS random sets of DOPAMINERGIC neurons,
each the same size as the real seed set, and run the identical pipeline.

    Why dopaminergic, not any neurons: dopamine neurons as a whole project
    heavily to the mushroom body. Against random neurons, every PD gene would
    "discover" the mushroom body. Against random DA neurons, a group only
    ranks high if THIS gene's clusters hit it more than dopamine neurons
    generally do. That is the gene-specific signal.

    A second, weaker null (random neurons of any type) is computed too and
    shown as "vs the whole brain". Headline numbers use the DA null.

Statistics per group:
    z       = (observed - null_mean) / null_sd     (null_sd floored at 1e-9)
    p       = (1 + #draws >= observed) / (1 + n_draws)   empirical, one-sided
    q       = Benjamini-Hochberg over all rankable groups at that level
    above_chance = q < config.FDR_ALPHA and z > 0

Why FDR: there are ~80 regions and thousands of cell types. At p < 0.05 a few
would light up by luck alone; BH keeps the expected share of false hits at 5%.

Speed: stack all draws as columns of one sparse x0 (n x 200) and call
propagate once. Each hop is one sparse matmul, so the baseline takes seconds,
not minutes. Fix the RNG (config.RANDOM_SEED) so reruns are identical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class NullDistribution:
    group_means: np.ndarray        # n_groups x n_draws
    disruption: np.ndarray         # n_draws


def draw_random_seeds(pool: np.ndarray, size: int, n_draws: int, rng: np.random.Generator) -> np.ndarray:
    """n_draws x size positions, each row sampled without replacement from pool.
    If size > len(pool), raise: the null is undefined."""
    raise NotImplementedError


def null_distribution(conn, seed_size: int, mode, strength: float, hops: int, decay: float,
                      group_codes: np.ndarray, n_groups: int, pool: np.ndarray) -> NullDistribution:
    """Run the full perturbation + propagation + aggregation for every random draw.

    Use the same mode and strength as the real run, so the only difference
    between observed and null is WHICH neurons were seeded.
    """
    raise NotImplementedError


def z_and_p(observed: np.ndarray, null: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """observed: n_groups; null: n_groups x n_draws. Returns (null_mean, null_sd, z, p)
    as defined in the module docstring."""
    raise NotImplementedError


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """q-values. Ignore NaN (unrankable groups) and return NaN for them."""
    raise NotImplementedError
