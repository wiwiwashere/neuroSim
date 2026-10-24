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

from neurosim import config
from neurosim.engine.perturb import initial_deficit
from neurosim.engine.propagate import propagate
from neurosim.engine.vulnerability import disruption_scores, group_means_batch

# Draws propagated per batch. 139k neurons x 25 draws keeps each hop's dense
# block near 30 MB, so the full baseline fits easily in a laptop's memory.
CHUNK = 25

@dataclass
class NullDistribution:
    group_means: np.ndarray        # n_groups x n_draws
    disruption: np.ndarray         # n_draws


def draw_random_seeds(pool: np.ndarray, size: int, n_draws: int, rng: np.random.Generator) -> np.ndarray:
    """n_draws x size positions, each row sampled without replacement from pool.
    If size > len(pool), raise: the null is undefined."""
    pool = np.asarray(pool, dtype=np.int64)
    if size > len(pool):
        raise ValueError(f"seed set of {size} neurons is larger than the pool of {len(pool)}: the null is undefined")
    if size < 1:
        raise ValueError("seed set is empty")
    return np.stack([rng.choice(pool, size=size, replace=False) for _ in range(n_draws)])


def null_distribution(conn, seed_size: int, mode, strength: float, hops: int, decay: float,
                      group_codes: np.ndarray, n_groups: int, pool: np.ndarray,
                      n_draws: int = config.N_RANDOM_DRAWS, random_seed: int = config.RANDOM_SEED) -> NullDistribution:
    """Run the full perturbation + propagation + aggregation for every random draw.

    Use the same mode and strength as the real run, so the only difference
    between observed and null is WHICH neurons were seeded.
    """
    means, disruption = null_distributions(conn, seed_size, mode, strength, hops, decay,
                                           {"groups": (group_codes, n_groups)}, pool, n_draws, random_seed)
    return NullDistribution(group_means=means["groups"], disruption=disruption)


def null_distributions(conn, seed_size: int, mode, strength: float, hops: int, decay: float,
                       groupings: dict, pool: np.ndarray, n_draws: int = config.N_RANDOM_DRAWS,
                       random_seed: int = config.RANDOM_SEED) -> tuple[dict, np.ndarray]:
    """null_distribution for several group levels from one set of draws.

    groupings maps a key to (group_codes, n_groups). Returns ({key: n_groups x
    n_draws group means}, n_draws disruption scores). Each draw is propagated
    once and aggregated at every level, in chunks of CHUNK draws.
    """
    rng = np.random.default_rng(random_seed)
    draws = draw_random_seeds(pool, seed_size, n_draws, rng)
    unit = initial_deficit(1, np.array([0]), mode, strength)[0]
    means = {key: [] for key in groupings}
    disruption = []
    for start in range(0, n_draws, CHUNK):
        block = draws[start:start + CHUNK]
        x0 = np.zeros((conn.n, len(block)))
        x0[block.T, np.arange(len(block))] = unit
        prop = propagate(conn.A, x0, hops, decay)
        for key, (codes, n_groups) in groupings.items():
            means[key].append(group_means_batch(prop.impact, prop.seed_mask, codes, n_groups))
        disruption.append(disruption_scores(prop.impact, prop.seed_mask, conn.in_strength, hops, decay))
    return {key: np.hstack(parts) for key, parts in means.items()}, np.concatenate(disruption)


def z_and_p(observed: np.ndarray, null: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """observed: n_groups; null: n_groups x n_draws. Returns (null_mean, null_sd, z, p)
    as defined in the module docstring."""
    observed = np.asarray(observed, dtype=float)
    null = np.asarray(null, dtype=float)
    with np.errstate(invalid="ignore"):
        null_mean = np.nanmean(null, axis=-1) if null.size else np.full(observed.shape, np.nan)
        null_sd = np.maximum(np.nanstd(null, axis=-1), 1e-9)
        z = (observed - null_mean) / null_sd
        n_draws = null.shape[-1]
        p = (1 + (null >= observed[..., None] - 1e-12).sum(axis=-1)) / (1 + n_draws)
    p = np.where(np.isnan(observed), np.nan, p)
    return null_mean, null_sd, z, p


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """q-values. Ignore NaN (unrankable groups) and return NaN for them."""
    p = np.asarray(p, dtype=float)
    q = np.full_like(p, np.nan)
    ok = np.flatnonzero(~np.isnan(p))
    if ok.size == 0:
        return q
    order = ok[np.argsort(p[ok], kind="stable")]
    m = len(order)
    ranked = p[order] * m / np.arange(1, m + 1)
    q[order] = np.minimum(np.minimum.accumulate(ranked[::-1])[::-1], 1.0)
    return q
