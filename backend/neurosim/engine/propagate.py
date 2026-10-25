"""Multi-hop impact propagation (CS1). See docs/ENGINE_DESIGN.md, section 5.

STATUS: placeholder. CS1 writes propagate. pipeline.py, the
validation script and the API already call it with the signatures
below, and the tests marked `needs_engine` turn green once it works.

    hop 1:  h1 = A @ x0              share of each neuron's input lost directly
    hop k:  hk = A @ h(k-1)          share of input coming from already-hit neurons
    impact  I  = sum_k decay**(k-1) * hk     for k = 1..hops

Reading the numbers:
    h1[j] = 0.30  ->  30% of neuron j's input came from the seeds.
    h2[j] = 0.10  ->  on average, j's inputs lost 10% of THEIR input.
    I[j] is a weighted sum of those, a ranking score, not a percentage.

Each hk stays between 0 and 1 because rows of A sum to at most 1 and x0 is
between 0 and 1. With decay 0.5 and 3 hops, I is at most 1.75.

Seeds are excluded from every reported score (their impact is trivially high),
but they are NOT removed from the matrix, so loops that pass back through a
seed still count. This keeps the model linear and simple.

Batching: x0 may be a matrix (n x k) to run k perturbations at once. The random
baseline runs 200 draws this way in one sparse matmul per hop.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp


@dataclass
class Propagation:
    per_hop: list[np.ndarray]     # [h1, h2, ..., hK], each n (or n x k)
    impact: np.ndarray            # weighted sum
    seed_mask: np.ndarray         # x0 > 0, same shape as x0 (per column for batches)

    @property
    def direct(self) -> np.ndarray:
        """h1: the most defensible number, shown first in the UI."""
        return self.per_hop[0]


def propagate(
    A: sp.csr_matrix,
    x0: np.ndarray,
    hops: int,
    decay: float,
) -> Propagation:
    """Run the recurrence above and return every hop plus the weighted sum.

    x0 may be 1-D (one run) or 2-D (one column per run). Use A @ x, never
    densify A. Set seed_mask = x0 > 0.
    """
    if hops < 1:
        raise ValueError("hops must be at least 1")

    x0 = np.asarray(x0, dtype=float)
    per_hop: list[np.ndarray] = []
    impact = np.zeros_like(x0, dtype=float)

    h = x0
    for k in range(1, hops + 1):
        h = A @ h  # hop k: share of input from neurons hit in the previous hop
        per_hop.append(np.asarray(h))
        impact = impact + (decay ** (k - 1)) * h

    return Propagation(
        per_hop=per_hop,
        impact=np.asarray(impact),
        seed_mask=x0 > 0,
    )
