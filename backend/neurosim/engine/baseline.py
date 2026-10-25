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

import warnings
from dataclasses import dataclass

import numpy as np

from neurosim import config
from neurosim.engine.perturb import initial_deficit
from neurosim.engine.propagate import propagate
from neurosim.engine.vulnerability import disruption_scores, group_means_batch

# Draws propagated together. 139k x 25 float64 is about 28 MB per hop.
DRAW_CHUNK = 25


@dataclass
class NullDistribution:
    group_means: np.ndarray        # n_groups x n_draws
    disruption: np.ndarray         # n_draws


def draw_random_seeds(pool: np.ndarray, size: int, n_draws: int, rng: np.random.Generator) -> np.ndarray:
    """n_draws x size positions, each row sampled without replacement from pool.
    If size > len(pool), raise: the null is undefined."""
    pool = np.asarray(pool, dtype=np.int64)
    if size < 1:
        raise ValueError("seed size must be at least 1")
    if size > len(pool):
        raise ValueError(f"cannot draw {size} seeds without replacement from a pool of {len(pool)}")
    out = np.empty((n_draws, size), dtype=np.int64)
    for i in range(n_draws):
        out[i] = rng.choice(pool, size=size, replace=False)
    return out


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
    n_draws group means}, n_draws disruption scores). The pipeline passes all
    four GroupLevels at once; the validation script passes one target set.
    """
    rng = np.random.default_rng(random_seed)
    seeds = draw_random_seeds(pool, seed_size, n_draws, rng)

    n = conn.n
    keys = list(groupings)
    group_parts: dict[str, list[np.ndarray]] = {k: [] for k in keys}
    disruption_parts: list[np.ndarray] = []

    for start in range(0, n_draws, DRAW_CHUNK):
        chunk = seeds[start:start + DRAW_CHUNK]
        x0 = np.column_stack([initial_deficit(n, row, mode, strength) for row in chunk])
        prop = propagate(conn.A, x0, hops, decay)

        for key in keys:
            codes, n_groups = groupings[key]
            group_parts[key].append(
                group_means_batch(prop.impact, prop.seed_mask, codes, n_groups)
            )
        disruption_parts.append(
            disruption_scores(prop.impact, prop.seed_mask, conn.in_strength, hops, decay)
        )

    means = {k: np.hstack(parts) for k, parts in group_parts.items()}
    disruption = np.concatenate(disruption_parts)
    return means, disruption


def z_and_p(observed: np.ndarray, null: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """observed: n_groups; null: n_groups x n_draws. Returns (null_mean, null_sd, z, p)
    as defined in the module docstring."""
    observed = np.asarray(observed, dtype=float)
    null = np.asarray(null, dtype=float)
    n_draws = null.shape[1]

    with warnings.catch_warnings():
        # Groups with all-NaN nulls would otherwise warn; they become NaN below.
        warnings.simplefilter("ignore", category=RuntimeWarning)
        null_mean = np.nanmean(null, axis=1)
        null_sd = np.maximum(np.nanstd(null, axis=1), 1e-9)

    with np.errstate(invalid="ignore", divide="ignore"):
        z = (observed - null_mean) / null_sd
        # NaN comparisons are False, so NaN null draws never count as exceedances.
        exceed = np.sum(null >= observed[:, None], axis=1)
        p = (1.0 + exceed) / (1.0 + n_draws)

    missing = np.isnan(observed)
    z = np.where(missing, np.nan, z)
    p = np.where(missing, np.nan, p)
    return null_mean, null_sd, z, p


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """q-values. Ignore NaN (unrankable groups) and return NaN for them."""
    p = np.asarray(p, dtype=float)
    q = np.full(p.shape, np.nan)
    valid = np.flatnonzero(~np.isnan(p))
    m = valid.size
    if m == 0:
        return q

    order = valid[np.argsort(p[valid], kind="stable")]
    ranked = p[order]
    ranks = np.arange(1, m + 1)
    adjusted = ranked * m / ranks
    # Enforce monotonicity: q_i = min over j >= i of adjusted_j.
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    q[order] = np.clip(adjusted, 0.0, 1.0)
    return q
