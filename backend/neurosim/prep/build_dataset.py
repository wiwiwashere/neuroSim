"""Offline prep (CS1): turn raw FlyWire downloads into four small files.

Run once:  python -m neurosim.prep.build_dataset

Inputs (data/raw/):
    proofread_connections_783.feather   Zenodo record 10676866. One row per
        (pre neuron, post neuron, neuropil) with a synapse count and average
        neurotransmitter probabilities. VERIFY column names on first load;
        expected roughly: pre_pt_root_id, post_pt_root_id, neuropil,
        syn_count, gaba_avg, ach_avg, glut_avg, oct_avg, ser_avg, da_avg.
    Codex CSVs (classification, cell types, neurotransmitter predictions).
        VERIFY names; expected roughly: root_id, super_class, class,
        cell_type / primary_type, side, nt_type, nt_type_score.

Outputs (data/processed/):
    neurons.parquet   one row per neuron, index = matrix position
    edges.npz         sparse synapse-count matrix W (pre x post), thresholded
    index.npy         matrix position -> root_id
    regions.json      neuropil -> super region -> plain-language function label

Decisions made here (details in docs/ENGINE_DESIGN.md, sections 2-3):
    * Sum synapse counts over neuropils per neuron pair, THEN threshold.
      A pair with 3 synapses in one neuropil and 3 in another is a real 6-synapse
      connection.
    * Threshold at config.SYNAPSE_THRESHOLD (5).
    * Each neuron's "region" = the neuropil where it RECEIVES the most synapses,
      because input is what a perturbation removes.
    * Edge neurotransmitter = the presynaptic neuron's predicted type (kept for
      the signed stretch; the MVP ignores sign).
"""

from __future__ import annotations

import pandas as pd
import scipy.sparse as sp

from neurosim import config


def load_connections() -> pd.DataFrame:
    """Read the proofread connections feather file from data/raw/.

    Returns the raw table. Print its columns and row count the first time and
    fix the expected names in the module docstring if they differ.
    """
    raise NotImplementedError


def load_annotations() -> pd.DataFrame:
    """Read and join the Codex CSVs into one table keyed by root_id.

    Keep: root_id, super_class, class, cell_type, side, nt_type, nt_type_score.
    A neuron missing a cell type keeps cell_type = None; do not drop it, it is
    still part of the wiring.
    """
    raise NotImplementedError


def aggregate_pairs(conn: pd.DataFrame) -> pd.DataFrame:
    """Sum syn_count over neuropils for each (pre, post) pair, then keep pairs
    with total >= config.SYNAPSE_THRESHOLD.

    Returns columns: pre, post, syn_count.
    Log how many pairs and synapses the threshold removed (goes in the README).
    """
    raise NotImplementedError


def primary_input_region(conn: pd.DataFrame) -> pd.Series:
    """For each post neuron, the neuropil with the largest summed syn_count.

    Returns a Series root_id -> neuropil name. Computed BEFORE thresholding so a
    neuron's region reflects all its input.
    """
    raise NotImplementedError


def build_matrix(pairs: pd.DataFrame, root_ids: list[int]) -> sp.csr_matrix:
    """Sparse matrix W with W[i, j] = synapses from neuron i to neuron j.

    Rows are presynaptic, columns postsynaptic, positions follow root_ids.
    Stored as raw counts; normalization happens at load time in engine/graph.py
    so we can change the normalization without re-running prep.
    """
    raise NotImplementedError


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
