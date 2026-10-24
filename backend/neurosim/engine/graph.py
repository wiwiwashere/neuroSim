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

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.sparse as sp

from neurosim import config

# Neuron table columns the engine reads. Missing label columns are filled with
# None (the neuron is then "unlabelled" at that level, never dropped).
LABEL_COLUMNS = ["region", "super_region", "cell_type", "super_class"]
DOPAMINE_LABELS = {"da", "dopamine"}


@dataclass
class Connectome:
    W: sp.csr_matrix              # pre x post synapse counts
    A: sp.csr_matrix              # post x pre input fractions (rows sum to 1 or 0)
    in_strength: np.ndarray       # total input synapses per neuron
    neurons: pd.DataFrame         # one row per matrix position
    root_ids: np.ndarray          # position -> root_id
    pos: dict[int, int]           # root_id -> position
    regions: dict = field(default_factory=dict)   # neuropil -> {super_region, function}

    @property
    def n(self) -> int:
        return self.W.shape[0]

    def positions(self, root_ids: list[int]) -> np.ndarray:
        """Matrix positions for these root IDs. Unknown IDs are an error, not skipped:
        a seed that silently vanishes would change the result without anyone noticing."""
        missing = [rid for rid in root_ids if int(rid) not in self.pos]
        if missing:
            raise KeyError(f"{len(missing)} root IDs not in the connectome, e.g. {missing[:3]}")
        return np.array([self.pos[int(rid)] for rid in root_ids], dtype=np.int64)

    def dopaminergic(self) -> np.ndarray:
        """Positions of all neurons whose predicted transmitter is dopamine.
        This is the pool the random baseline draws from (ENGINE_DESIGN.md, section 7)."""
        nt = self.neurons["nt_type"].astype("string").str.lower()
        return np.flatnonzero(nt.isin(DOPAMINE_LABELS).fillna(False).to_numpy())

    def function_label(self, group: str) -> str | None:
        """Plain-language function for a region or super region, if Bio wrote one."""
        if group in self.regions:
            return self.regions[group].get("function")
        for info in self.regions.values():
            if info.get("super_region") == group:
                return info.get("function")
        return None


def input_normalize(W: sp.csr_matrix) -> tuple[sp.csr_matrix, np.ndarray]:
    """Build A from W.

    Steps: in = column sums of W; scale each column j of W by 1 / in_j
    (leave columns with in_j = 0 as zeros); transpose so rows are targets.
    Returns (A as CSR, in_strength).

    Test: every row of A sums to 1.0 (within 1e-9) or 0.0.
    """
    W = sp.csr_matrix(W, dtype=float)
    in_strength = np.asarray(W.sum(axis=0)).ravel()
    inv = np.divide(1.0, in_strength, out=np.zeros_like(in_strength), where=in_strength > 0)
    A = (W @ sp.diags(inv)).T.tocsr()
    A.eliminate_zeros()
    return A, in_strength


def build_connectome(W: sp.spmatrix, neurons: pd.DataFrame, root_ids: np.ndarray, regions: dict | None = None) -> Connectome:
    """Assemble a Connectome from W and a neuron table whose rows follow matrix
    positions. Used by load_connectome and by synthetic graphs in tests."""
    W = sp.csr_matrix(W, dtype=float)
    root_ids = np.asarray(root_ids, dtype=np.int64)
    if W.shape != (len(root_ids), len(root_ids)) or len(neurons) != len(root_ids):
        raise ValueError(f"shape mismatch: W {W.shape}, {len(root_ids)} root IDs, {len(neurons)} neuron rows")
    regions = regions or {}
    neurons = neurons.reset_index(drop=True).copy()
    neurons["root_id"] = root_ids
    for col in LABEL_COLUMNS + ["nt_type"]:
        if col not in neurons:
            neurons[col] = None
    if regions and neurons["super_region"].isna().all():
        neurons["super_region"] = neurons["region"].map(lambda r: regions.get(r, {}).get("super_region"))
    A, in_strength = input_normalize(W)
    pos = {int(rid): i for i, rid in enumerate(root_ids)}
    return Connectome(W=W, A=A, in_strength=in_strength, neurons=neurons, root_ids=root_ids, pos=pos, regions=regions)


def processed_data_available() -> bool:
    return all((config.PROCESSED_DIR / f).exists() for f in ("edges.npz", "index.npy", "neurons.parquet"))


_CACHE: Connectome | None = None


def set_connectome(conn: Connectome | None) -> None:
    """Replace the process-wide connectome (synthetic graphs, tests). None clears it."""
    global _CACHE
    _CACHE = conn


def load_connectome() -> Connectome:
    """Load data/processed/* once per process and keep it in memory.

    ~139k neurons and a few million edges fit comfortably in RAM as scipy
    sparse matrices; load time should be a few seconds.
    """
    global _CACHE
    if _CACHE is None:
        d = config.PROCESSED_DIR
        W = sp.load_npz(d / "edges.npz")
        root_ids = np.load(d / "index.npy")
        neurons = pd.read_parquet(d / "neurons.parquet")
        regions_path = d / "regions.json"
        regions = json.loads(regions_path.read_text()) if regions_path.exists() else {}
        _CACHE = build_connectome(W, neurons, root_ids, regions)
    return _CACHE
