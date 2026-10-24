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

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather
import scipy.sparse as sp

from neurosim import config

CONNECTIONS_FILE = "proofread_connections_783.feather"
ANNOTATIONS_FILE = "flywire_neuron_annotations_783.tsv"

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
# The annotation file spells transmitters out in lower case. known_nt (from
# the literature) also names histamine and tyramine, which the synapse
# predictions do not cover.
NT_NAMES = {
    "acetylcholine": "ACH",
    "gaba": "GABA",
    "glutamate": "GLUT",
    "octopamine": "OCT",
    "serotonin": "SER",
    "dopamine": "DA",
    "histamine": "HA",
    "tyramine": "TYR",
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



def load_annotations(path: Path | None = None) -> pd.DataFrame | None:
    """Read the neuron annotation TSV into one table keyed by root_id.

    Keeps: root_id, super_class, class, sub_class, cell_type, hemibrain_type,
    side, flow, and nt_type (Codex code) with nt_type_score and nt_source
    ("known" from the literature, else "predicted" from synapses). A neuron missing a
    cell type keeps cell_type = None; do not drop it, it is still part of the
    wiring. Returns None when the file has not been downloaded yet.
    """
    path = Path(path or config.RAW_DIR / ANNOTATIONS_FILE)
    if not path.exists():
        return None
    wanted = {"root_id", "super_class", "cell_class", "cell_sub_class", "cell_type",
              "hemibrain_type", "side", "flow", "top_nt", "top_nt_conf", "known_nt"}
    labels = pd.read_csv(path, sep="\t", dtype={"root_id": "int64"}, usecols=lambda c: c in wanted,
                         low_memory=False)
    missing = {"root_id", "cell_type"} - set(labels.columns)
    if missing:
        raise ValueError(f"{path.name} lacks columns {sorted(missing)}")
    labels = labels.rename(columns={"cell_class": "class", "cell_sub_class": "sub_class"})

    # Literature transmitter first, synapse prediction second. This matters:
    # top_nt calls ~5,200 Kenyon cells dopaminergic, while known_nt says they
    # are cholinergic. Without this the random DA baseline would be mostly
    # Kenyon cells.
    empty = pd.Series(np.nan, index=labels.index, dtype=object)
    known = labels.pop("known_nt").map(_first_transmitter, na_action="ignore") if "known_nt" in labels else empty
    top = labels.pop("top_nt").str.lower().map(NT_NAMES) if "top_nt" in labels else empty
    score = labels.pop("top_nt_conf").astype(float) if "top_nt_conf" in labels else empty.astype(float)
    labels["nt_type"] = known.fillna(top)
    labels["nt_type_score"] = score.where(known.isna())
    labels["nt_source"] = np.where(known.notna(), "known", np.where(top.notna(), "predicted", None))
    return labels.drop_duplicates("root_id").reset_index(drop=True)

def _first_transmitter(known_nt: str) -> str | None:
    """'acetylcholine; sNPF; acetylcholine, sNPF' -> 'ACH'. Peptides and
    'gaba-negative' style entries are skipped."""
    for name in known_nt.replace(",", ";").split(";"):
        code = NT_NAMES.get(name.strip().lower())
        if code:
            return code
    return None


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


def neuron_transmitter(conn: pd.DataFrame) -> pd.DataFrame:
    """Each presynaptic neuron's predicted transmitter, from its own synapses.

    Each row of the file carries the mean transmitter probabilities over that
    row's synapses. Weighting by syn_count and summing per pre neuron gives
    the mean over all of the neuron's output synapses, the neuron-level vote
    FlyWire uses. Returns nt_type (Codex code) and nt_type_score (the winning
    mean probability), indexed by root_id.
    """
    pre_ids, pre_codes = np.unique(conn[PRE].to_numpy(np.int64), return_inverse=True)
    # Rows without a prediction (NaN) count for nothing, in the vote and the total.
    weight = conn["syn_count"].to_numpy(np.float64)
    for col in NT_COLUMNS:
        weight[np.isnan(conn[col].to_numpy())] = 0.0
    total = np.bincount(pre_codes, weights=weight, minlength=len(pre_ids))
    votes = np.column_stack([
        np.bincount(pre_codes, weights=weight * np.nan_to_num(conn[col].to_numpy(np.float64)),
                    minlength=len(pre_ids))
        for col in NT_COLUMNS
    ])
    has_vote = total > 0
    probs = votes[has_vote] / total[has_vote, None]
    best = probs.argmax(axis=1)
    return pd.DataFrame(
        {"nt_type": np.array(list(NT_COLUMNS.values()))[best],
         "nt_type_score": probs[np.arange(len(best)), best]},
        index=pd.Index(pre_ids[has_vote], name="root_id"),
    )


def build_matrix(pairs: pd.DataFrame, root_ids: np.ndarray) -> sp.csr_matrix:
    """Sparse matrix W with W[i, j] = synapses from neuron i to neuron j.

    Rows are presynaptic, columns postsynaptic, positions follow root_ids
    (sorted and unique). Stored as raw int32 counts; normalization happens at
    load time in engine/graph.py so we can change the normalization without
    re-running prep.
    """
    root_ids = np.asarray(root_ids, dtype=np.int64)
    if np.any(np.diff(root_ids) <= 0):
        raise ValueError("root_ids must be sorted and unique")
    rows = _positions(root_ids, pairs["pre"].to_numpy(np.int64))
    cols = _positions(root_ids, pairs["post"].to_numpy(np.int64))
    n = len(root_ids)
    W = sp.csr_matrix((pairs["syn_count"].to_numpy(np.int32), (rows, cols)), shape=(n, n))
    W.sum_duplicates()
    return W


def _positions(root_ids: np.ndarray, ids: np.ndarray) -> np.ndarray:
    pos = np.searchsorted(root_ids, ids)
    found = pos < len(root_ids)
    found[found] = root_ids[pos[found]] == ids[found]
    if not found.all():
        raise ValueError(f"{int((~found).sum())} pair endpoints are not in root_ids")
    return pos


# Super regions follow the standard neuropil groups (Ito et al. 2014) that
# FlyWire uses. Function labels are short, textbook-level summaries; Bio owns
# the wording, so edit them here and re-run prep.
SUPER_REGIONS = {
    "optic lobe": (["LA", "ME", "AME", "LO", "LOP"], "vision"),
    "ocellar ganglion": (["OCG"], "light sensing by the ocelli"),
    "mushroom body": (["MB_CA", "MB_PED", "MB_VL", "MB_ML"], "learning and memory"),
    "central complex": (["FB", "EB", "PB", "NO"], "navigation and locomotor control"),
    "lateral complex": (["LAL", "BU", "GA"], "steering, central complex output"),
    "antennal lobe": (["AL"], "smell, first relay"),
    "lateral horn": (["LH"], "innate responses to odors"),
    "superior neuropils": (["SLP", "SIP", "SMP"], "integration, incl. mushroom body output"),
    "inferior neuropils": (["CRE", "SCL", "ICL", "IB", "ATL"], "multisensory integration"),
    "ventrolateral neuropils": (["AOTU", "AVLP", "PVLP", "PLP", "WED"], "higher visual and auditory processing"),
    "ventromedial neuropils": (["VES", "EPA", "GOR", "SPS", "IPS"], "premotor and descending control"),
    "periesophageal neuropils": (["SAD", "AMMC", "FLA", "CAN", "PRW"], "hearing, touch, taste and feeding"),
    "gnathal ganglia": (["GNG"], "taste, feeding, mouth and neck motor output"),
}
UNASSIGNED = {"super_region": "unassigned", "function": "synapses outside any named neuropil"}


def build_region_table(neuropils: list[str]) -> dict:
    """Map each FlyWire neuropil to a super region and a plain-language label.

    Example: "MB_ML_R" -> {"super_region": "mushroom body",
                            "function": "learning and memory", "side": "right"}.
    Anything not in SUPER_REGIONS (only UNASGD in v783) maps to "unassigned".
    """
    by_base = {base: (sr, fn) for sr, (bases, fn) in SUPER_REGIONS.items() for base in bases}
    table = {}
    for name in sorted(neuropils):
        base, side = name, None
        if name.endswith(("_L", "_R")):
            base, side = name[:-2], "left" if name.endswith("_L") else "right"
        if base in by_base:
            sr, fn = by_base[base]
            table[name] = {"super_region": sr, "function": fn, "side": side}
        else:
            table[name] = {**UNASSIGNED, "side": side}
    return table


LABEL_COLUMNS = ["super_class", "class", "sub_class", "cell_type", "hemibrain_type", "side", "flow"]


def build_neuron_table(root_ids: np.ndarray, W: sp.csr_matrix, region: pd.Series,
                       nt: pd.DataFrame, labels: pd.DataFrame | None, regions: dict) -> pd.DataFrame:
    """One row per matrix position: root_id, region, super_region, labels,
    transmitter, and input/output synapse totals after thresholding."""
    root_ids = np.asarray(root_ids, dtype=np.int64)
    neurons = pd.DataFrame({"root_id": root_ids})
    neurons["region"] = region.reindex(root_ids).to_numpy()
    neurons["super_region"] = neurons["region"].map(lambda r: regions[r]["super_region"], na_action="ignore")
    neurons["in_syn"] = np.asarray(W.sum(axis=0)).ravel().astype(np.int64)
    neurons["out_syn"] = np.asarray(W.sum(axis=1)).ravel().astype(np.int64)

    lab = labels.set_index("root_id") if labels is not None else pd.DataFrame(index=pd.Index([], dtype="int64"))
    lab = lab.reindex(index=root_ids, columns=LABEL_COLUMNS + ["nt_type", "nt_type_score", "nt_source"])
    for col in LABEL_COLUMNS:
        neurons[col] = lab[col].to_numpy()
    # Neurons without an annotated side take the side of their input neuropil.
    region_side = neurons["region"].map(lambda r: regions[r]["side"], na_action="ignore")
    neurons["side"] = neurons["side"].fillna(region_side)

    derived = nt.reindex(root_ids)
    annotated = lab["nt_type"].notna().to_numpy()
    neurons["nt_type"] = np.where(annotated, lab["nt_type"], derived["nt_type"])
    neurons["nt_type_score"] = np.where(annotated, lab["nt_type_score"].astype(float),
                                        derived["nt_type_score"])
    neurons["nt_source"] = np.where(annotated, lab["nt_source"],
                                    np.where(derived["nt_type"].notna(), "synapses", None))

    # Parquet wants None, not NaN, in text columns.
    for col in neurons.columns[neurons.dtypes == object]:
        neurons[col] = neurons[col].astype(object).where(neurons[col].notna(), None)
    return neurons


def build(raw_dir: Path = config.RAW_DIR, out_dir: Path = config.PROCESSED_DIR,
          threshold: int = config.SYNAPSE_THRESHOLD) -> dict:
    """Run every step above, write out_dir/*, and return the summary."""
    t0 = time.time()
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    print(f"Reading {raw_dir / CONNECTIONS_FILE}")
    conn = load_connections(raw_dir / CONNECTIONS_FILE, WIRING_COLUMNS)
    print(f"  {len(conn):,} rows, {int(conn['syn_count'].sum()):,} synapses")
    region = primary_input_region(conn)
    neuropils = list(conn["neuropil"].cat.categories)
    connected = np.union1d(conn[PRE].unique(), conn[POST].unique())
    pairs = aggregate_pairs(conn, threshold)
    del conn
    nt = neuron_transmitter(load_connections(raw_dir / CONNECTIONS_FILE, [PRE, "syn_count", *NT_COLUMNS]))

    labels = load_annotations(raw_dir / ANNOTATIONS_FILE)
    if labels is None:
        print(f"  no {ANNOTATIONS_FILE}: cell types stay empty (run prep/download_labels.py first)")
        root_ids = connected
    else:
        # Annotated neurons without connections stay in as isolated rows, so a
        # seed picked from the labels always resolves to a matrix position.
        root_ids = np.union1d(connected, labels["root_id"].to_numpy(np.int64))

    W = build_matrix(pairs, root_ids)
    regions = build_region_table(neuropils)
    neurons = build_neuron_table(root_ids, W, region, nt, labels, regions)

    types = pd.Series(neurons["cell_type"].dropna().unique(), dtype=str)
    summary = {
        "neurons": int(len(neurons)),
        "neurons_with_connections": int(len(connected)),
        "neurons_with_cell_type": int(neurons["cell_type"].notna().sum()),
        "edges": int(W.nnz),
        "synapses_kept": int(W.sum()),
        "synapse_threshold": threshold,
        "dopaminergic": int((neurons["nt_type"] == "DA").sum()),
        "ppl1_types": sorted(types[types.str.startswith("PPL1")]),
        "pam_types": sorted(types[types.str.startswith("PAM")]),
    }
    write_outputs(out_dir, W, root_ids, neurons, regions, summary)
    summary["seconds"] = round(time.time() - t0, 1)
    return summary


def write_outputs(out_dir: Path, W: sp.csr_matrix, root_ids: np.ndarray, neurons: pd.DataFrame,
                  regions: dict, summary: dict) -> None:
    """Write the five files in data/processed/ that engine/graph.py reads."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sp.save_npz(out_dir / "edges.npz", W, compressed=True)
    np.save(out_dir / "index.npy", np.asarray(root_ids, dtype=np.int64))
    neurons.to_parquet(out_dir / "neurons.parquet")
    (out_dir / "regions.json").write_text(json.dumps(regions, indent=2) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def main(argv: list[str] | None = None) -> None:
    """Build data/processed/* and print a summary: neurons, edges after
    threshold, number of dopaminergic neurons, and which PPL1* and PAM* cell
    types were found (the hour-4 gate)."""
    parser = argparse.ArgumentParser(description="Build data/processed/ from the raw FlyWire files.")
    parser.add_argument("--raw-dir", type=Path, default=config.RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=config.PROCESSED_DIR)
    parser.add_argument("--threshold", type=int, default=config.SYNAPSE_THRESHOLD)
    args = parser.parse_args(argv)

    s = build(args.raw_dir, args.out_dir, args.threshold)
    print(f"\nWrote {args.out_dir} in {s['seconds']}s")
    print(f"  neurons: {s['neurons']:,} ({s['neurons_with_connections']:,} connected, "
          f"{s['neurons_with_cell_type']:,} with a cell type)")
    print(f"  edges with >= {s['synapse_threshold']} synapses: {s['edges']:,} ({s['synapses_kept']:,} synapses)")
    print(f"  dopaminergic neurons: {s['dopaminergic']:,}")
    print(f"  PPL1 types ({len(s['ppl1_types'])}): {', '.join(s['ppl1_types']) or 'none'}")
    print(f"  PAM types ({len(s['pam_types'])}): {', '.join(s['pam_types']) or 'none'}")


if __name__ == "__main__":
    main()
