"""Offline prep (CS1): turn raw FlyWire downloads into four small files.

Run once:  python -m neurosim.prep.build_dataset

Inputs (data/raw/):
    proofread_connections_783.feather   Zenodo record 10676866. One row per
        (pre neuron, post neuron, neuropil), 16.8M rows. Columns:
        pre_pt_root_id, post_pt_root_id (int64), neuropil (79 names),
        syn_count, and the mean per-synapse transmitter probabilities
        gaba_avg, ach_avg, glut_avg, oct_avg, ser_avg, da_avg.
    flywire_neuron_annotations_783.tsv  Optional; written by
        prep/download_labels.py (flywire_annotations v3.2.0). One row per
        neuron. Used: root_id, super_class, cell_class, cell_sub_class,
        cell_type, hemibrain_type, side, flow, top_nt, top_nt_conf, known_nt.

Outputs (data/processed/):
    neurons.parquet   one row per neuron, index = matrix position
    edges.npz         sparse synapse-count matrix W (pre x post), thresholded
    index.npy         matrix position -> root_id
    regions.json      neuropil -> super region -> plain-language function label
    summary.json      the counts printed at the end of a run

Decisions made here (details in docs/ENGINE_DESIGN.md, sections 2-3):
    * Sum synapse counts over neuropils per neuron pair, THEN threshold.
      A pair with 3 synapses in one neuropil and 3 in another is a real 6-synapse
      connection.
    * Threshold at config.SYNAPSE_THRESHOLD (5).
    * Each neuron's "region" = the neuropil where it RECEIVES the most synapses,
      because input is what a perturbation removes.
    * A neuron's transmitter (nt_type) is, in order: the annotation's known_nt
      (literature), its top_nt (synapse prediction), or our own synapse-weighted
      vote over the neuron's output synapses. Codes follow Codex (ACH, GABA,
      GLUT, OCT, SER, DA) plus HA and TYR from known_nt. The random baseline
      draws from nt_type == "DA" (610 neurons, 331 of them annotated DANs).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather
import scipy.sparse as sp

from neurosim import config

CONNECTIONS_FILE = "proofread_connections_783.feather"

PRE, POST = "pre_pt_root_id", "post_pt_root_id"

# Per-synapse probability column -> transmitter code.
NT_COLUMNS = {
    "ach_avg": "ACH",
    "gaba_avg": "GABA",
    "glut_avg": "GLUT",
    "oct_avg": "OCT",
    "ser_avg": "SER",
    "da_avg": "DA",
}


WIRING_COLUMNS = [PRE, POST, "neuropil", "syn_count"]


def load_connections(path: Path | None = None, columns: list[str] | None = None) -> pd.DataFrame:
    """Read the proofread connections feather file from data/raw/.

    Returns the raw table (or just `columns`) with compact dtypes: int64 root
    IDs, a categorical neuropil, int32 syn_count and float32 transmitter
    probabilities. All columns of the full file take ~0.8 GB, so build() reads
    the wiring and the transmitter columns in two passes.
    """
    path = Path(path or config.RAW_DIR / CONNECTIONS_FILE)
    columns = columns or WIRING_COLUMNS + list(NT_COLUMNS)
    table = feather.read_table(path, columns=columns, memory_map=True)
    data = {}
    for name in columns:
        col = table.column(name)
        if name == "neuropil":
            encoded = col.combine_chunks().dictionary_encode()
            data[name] = pd.Categorical.from_codes(
                encoded.indices.to_numpy(zero_copy_only=False),
                categories=encoded.dictionary.to_pylist(),
            )
        elif name in (PRE, POST):
            data[name] = col.to_numpy()
        elif name == "syn_count":
            data[name] = pc.cast(col, pa.int32()).to_numpy()
        else:
            # ~1.7k rows have no prediction; they become NaN.
            data[name] = pc.cast(col, pa.float32()).to_numpy()
    del table
    return pd.DataFrame(data, copy=False)


def load_annotations() -> pd.DataFrame:
    """Read and join the Codex CSVs into one table keyed by root_id.

    Keep: root_id, super_class, class, cell_type, side, nt_type, nt_type_score.
    A neuron missing a cell type keeps cell_type = None; do not drop it, it is
    still part of the wiring.
    """
    raise NotImplementedError


def aggregate_pairs(conn: pd.DataFrame, threshold: int = config.SYNAPSE_THRESHOLD) -> pd.DataFrame:
    """Sum syn_count over neuropils for each (pre, post) pair, then keep pairs
    with total >= threshold.

    Returns columns: pre, post, syn_count, sorted by (pre, post).
    Prints how many pairs and synapses the threshold removed.
    """
    pre = conn[PRE].to_numpy(np.int64)
    post = conn[POST].to_numpy(np.int64)
    ids = np.union1d(np.unique(pre), np.unique(post))
    # Building a sparse matrix sums the per-neuropil rows of each pair.
    counts = sp.csr_matrix(
        (conn["syn_count"].to_numpy(np.int32), (_positions(ids, pre), _positions(ids, post))),
        shape=(len(ids), len(ids)),
    )
    counts.sum_duplicates()
    keep = counts.data >= threshold
    print(f"  pairs: {counts.nnz:,}; {int((~keep).sum()):,} below {threshold} synapses dropped "
          f"({int(counts.data[~keep].sum()):,} of {int(counts.data.sum()):,} synapses)")
    counts.data[~keep] = 0
    counts.eliminate_zeros()
    kept = counts.tocoo()
    return pd.DataFrame({
        "pre": ids[kept.row],
        "post": ids[kept.col],
        "syn_count": kept.data.astype(np.int64),
    })


def primary_input_region(conn: pd.DataFrame) -> pd.Series:
    """For each post neuron, the neuropil with the largest summed syn_count.

    Returns a Series root_id -> neuropil name. Computed BEFORE thresholding so a
    neuron's region reflects all its input. Ties go to the neuropil that comes
    first alphabetically.
    """
    post_ids, post_codes = np.unique(conn[POST].to_numpy(np.int64), return_inverse=True)
    neuropil = conn["neuropil"].astype("category")
    counts = sp.csr_matrix(
        (conn["syn_count"].to_numpy(np.float32), (post_codes, neuropil.cat.codes.to_numpy())),
        shape=(len(post_ids), len(neuropil.cat.categories)),
    )
    best = np.asarray(counts.argmax(axis=1)).ravel()
    return pd.Series(np.asarray(neuropil.cat.categories)[best], index=post_ids, name="region")


def build_matrix(pairs: pd.DataFrame, root_ids: list[int]) -> sp.csr_matrix:
    """Sparse matrix W with W[i, j] = synapses from neuron i to neuron j.

    Rows are presynaptic, columns postsynaptic, positions follow root_ids.
    Stored as raw counts; normalization happens at load time in engine/graph.py
    so we can change the normalization without re-running prep.
    """
    raise NotImplementedError


def _positions(root_ids: np.ndarray, ids: np.ndarray) -> np.ndarray:
    pos = np.searchsorted(root_ids, ids)
    found = pos < len(root_ids)
    found[found] = root_ids[pos[found]] == ids[found]
    if not found.all():
        raise ValueError(f"{int((~found).sum())} pair endpoints are not in root_ids")
    return pos


def build_region_table() -> dict:
    """Map each FlyWire neuropil to a super region and a plain-language label.

    Example: "MB_ML_R" -> {"super_region": "mushroom body",
                            "function": "learning and memory"}.
    Bio writes the function labels; keep them short and defensible.
    """
    raise NotImplementedError


def main() -> None:
    """Run every step above and write data/processed/*.

    Print a summary: neurons, edges after threshold, number of dopaminergic
    neurons, and how many PPL1* and PAM* cell types were found (the hour-4 gate).
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
