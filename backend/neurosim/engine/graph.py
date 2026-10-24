"""The connectome as matrices (CS1). See docs/ENGINE_DESIGN.md, sections 2-3.

Two matrices matter:

    W   raw synapse counts, W[i, j] = synapses from neuron i onto neuron j.
    A   the propagation matrix, A[j, i] = W[i, j] / in_j, where
        in_j = sum_k W[k, j] is neuron j's total input (after thresholding).

So row j of A lists "what share of j's input comes from each upstream neuron",
and every non-empty row of A sums to exactly 1. That one property is what makes
every impact score below easy to interpret (it can never exceed 1 per hop).

Neurons with no input (in_j = 0, e.g. many sensory neurons) get an all-zero
row: nothing upstream can affect them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.sparse as sp


@dataclass
class Connectome:
    W: sp.csr_matrix              # pre x post synapse counts
    A: sp.csr_matrix              # post x pre input fractions (rows sum to 1 or 0)
    in_strength: np.ndarray       # total input synapses per neuron
    neurons: pd.DataFrame         # one row per matrix position
    root_ids: np.ndarray          # position -> root_id
    pos: dict[int, int]           # root_id -> position

    @property
    def n(self) -> int:
        return self.W.shape[0]

    def positions(self, root_ids: list[int]) -> np.ndarray:
        """Matrix positions for these root IDs. Unknown IDs are an error, not skipped:
        a seed that silently vanishes would change the result without anyone noticing."""
        raise NotImplementedError

    def dopaminergic(self) -> np.ndarray:
        """Positions of all neurons whose predicted transmitter is dopamine.
        This is the pool the random baseline draws from (ENGINE_DESIGN.md, section 7)."""
        raise NotImplementedError


def input_normalize(W: sp.csr_matrix) -> tuple[sp.csr_matrix, np.ndarray]:
    """Build A from W.

    Steps: in = column sums of W; scale each column j of W by 1 / in_j
    (leave columns with in_j = 0 as zeros); transpose so rows are targets.
    Returns (A as CSR, in_strength).

    Test: every row of A sums to 1.0 (within 1e-9) or 0.0.
    """
    raise NotImplementedError


_CACHE: Connectome | None = None


def load_connectome() -> Connectome:
    """Load data/processed/* once per process and keep it in memory.

    ~139k neurons and a few million edges fit comfortably in RAM as scipy
    sparse matrices; load time should be a few seconds.
    """
    raise NotImplementedError
