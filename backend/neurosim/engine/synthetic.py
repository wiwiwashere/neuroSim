"""A small synthetic fly brain for tests and the validation script (CS1).

Every neuron and synapse here is MADE UP. The graph exists so the whole
pipeline (seeds, propagation, baseline, grouping, drawing) can run end to end
before data/processed exists, and so the PAM validation has a planted answer
to recover.

What is wired in on purpose, loosely following the mushroom body layout:

    * Dopamine clusters with real cell-type names: PAM01-15 and PPL101-106
      each innervate their mushroom body compartments (hemibrain naming,
      Li et al. 2020), plus a few non-MB clusters (PPM3, PAL, PPL2, PPM1/2)
      with made-up type names so the random-DA pool is not all mushroom body.
    * One MBON type per compartment ("MBON_b'2" etc.) that gets a large share
      of its input from that compartment's DA neurons and its Kenyon cells.
    * Kenyon cells per lobe system (KCg, KCab, KCapbp) feeding the MBONs of
      the compartments they run through.
    * Background regions (lateral horn, central complex, superior neuropils,
      optic lobe, gnathal ganglia) with random sparse wiring, and MBON outputs
      into them, so effects can spread and the null has spread.

Root IDs start at 900000000000000000 so they can never be mistaken for
FlyWire IDs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp

from neurosim.engine.graph import Connectome, build_connectome

ROOT_ID_BASE = 900_000_000_000_000_000

# compartment -> neuropil
COMPARTMENTS = {
    "g1": "MB_PED_R", "g2": "MB_PED_R", "ped": "MB_PED_R",
    "g3": "MB_ML_R", "g4": "MB_ML_R", "g5": "MB_ML_R",
    "b1": "MB_ML_R", "b2": "MB_ML_R", "b'1": "MB_ML_R", "b'2": "MB_ML_R",
    "a1": "MB_VL_R", "a2": "MB_VL_R", "a3": "MB_VL_R",
    "a'1": "MB_VL_R", "a'2": "MB_VL_R", "a'3": "MB_VL_R",
}

# DA cell type -> (cluster, compartments or neuropils it innervates, n neurons)
DA_TYPES = {
    "PAM01": ("PAM", ["g5"], 8),
    "PAM02": ("PAM", ["b'2"], 4),
    "PAM03": ("PAM", ["b2", "b'2"], 3),
    "PAM04": ("PAM", ["b2"], 6),
    "PAM05": ("PAM", ["b'2"], 3),
    "PAM06": ("PAM", ["b'2"], 4),
    "PAM07": ("PAM", ["g4"], 6),
    "PAM08": ("PAM", ["g4"], 8),
    "PAM09": ("PAM", ["b1", "ped"], 3),
    "PAM10": ("PAM", ["b1"], 4),
    "PAM11": ("PAM", ["a1"], 3),
    "PAM12": ("PAM", ["g3"], 6),
    "PAM13": ("PAM", ["b'1"], 2),
    "PAM14": ("PAM", ["b'1"], 2),
    "PAM15": ("PAM", ["g5", "b'2"], 3),
    "PPL101": ("PPL1", ["g1", "ped"], 1),
    "PPL102": ("PPL1", ["g1"], 1),
    "PPL103": ("PPL1", ["g2", "a'1"], 1),
    "PPL104": ("PPL1", ["a'3"], 1),
    "PPL105": ("PPL1", ["a'2", "a2"], 1),
    "PPL106": ("PPL1", ["a3"], 1),
    "PPM3_syn": ("PPM3", ["FB_R", "EB"], 8),
    "PAL_syn": ("PAL", ["SMP_R"], 4),
    "PPL2_syn": ("PPL2", ["LH_R"], 6),
    "PPM12_syn": ("PPM1/2", ["GNG", "SMP_R"], 8),
}

KC_LOBES = {
    "KCg": ["g1", "g2", "g3", "g4", "g5"],
    "KCab": ["ped", "a1", "a2", "a3", "b1", "b2"],
    "KCapbp": ["a'1", "a'2", "a'3", "b'1", "b'2"],
}

# neuropil -> (super region, function label, n background neurons)
BACKGROUND = {
    "LH_R": ("lateral horn", "innate odour responses", 120),
    "FB_R": ("central complex", "navigation and walking", 80),
    "EB": ("central complex", "navigation and walking", 60),
    "SMP_R": ("superior neuropils", "integration and action selection", 160),
    "SIP_R": ("superior neuropils", "integration and action selection", 80),
    "ME_R": ("optic lobe", "vision", 200),
    "LO_R": ("optic lobe", "vision", 100),
    "GNG": ("gnathal ganglia", "feeding and motor output", 80),
}

MB_SUPER = ("mushroom body", "learning and memory")


def regions_table() -> dict:
    regions = {name: {"super_region": sr, "function": fn} for name, (sr, fn, _) in BACKGROUND.items()}
    for neuropil in set(COMPARTMENTS.values()) | {"MB_CA_R"}:
        regions[neuropil] = {"super_region": MB_SUPER[0], "function": MB_SUPER[1]}
    return regions


def synthetic_connectome(seed: int = 7) -> Connectome:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []

    def add(n: int, **labels) -> np.ndarray:
        start = len(rows)
        rows.extend(dict(labels) for _ in range(n))
        return np.arange(start, start + n)

    da = {t: add(n, cell_type=t, cluster=c, region=_region(targets[0]), super_class="central", nt_type="DA")
          for t, (c, targets, n) in DA_TYPES.items()}
    mbons = {c: add(2, cell_type=f"MBON_{c}", region=COMPARTMENTS[c], super_class="central",
                    nt_type=rng.choice(["ACH", "GABA", "GLUT"]))
             for c in COMPARTMENTS}
    kcs = {t: add(40, cell_type=t, region="MB_CA_R", super_class="central", nt_type="ACH") for t in KC_LOBES}
    background = {r: add(n, cell_type=f"{r.split('_')[0]}_local{i % 6}", region=r, super_class="central",
                         nt_type=rng.choice(["ACH", "GABA", "GLUT"], p=[0.6, 0.25, 0.15]))
                  for i, (r, (_, _, n)) in enumerate(BACKGROUND.items())}
    sensory = add(60, cell_type="ORN_syn", region=None, super_class="sensory", nt_type="ACH")

    n = len(rows)
    edges: dict[tuple[int, int], float] = {}

    def connect(pre, post, low: int, high: int, p: float = 1.0):
        for i in np.atleast_1d(pre):
            for j in np.atleast_1d(post):
                if i != j and rng.random() < p:
                    edges[(i, j)] = edges.get((i, j), 0) + rng.integers(low, high)

    # Sensory input reaches KCs (via a stand-in for projection neurons) and the lateral horn.
    for kc in kcs.values():
        connect(sensory, kc, 5, 15, p=0.15)
    connect(sensory, background["LH_R"], 5, 20, p=0.1)

    # Kenyon cells drive the MBONs of every compartment they run through.
    for kc_type, comps in KC_LOBES.items():
        for c in comps:
            connect(kcs[kc_type], mbons[c], 5, 12, p=0.6)

    # DA neurons innervate their compartments (MBONs and passing KC axons) or neuropils.
    for t, (_, targets, _) in DA_TYPES.items():
        for target in targets:
            if target in COMPARTMENTS:
                connect(da[t], mbons[target], 20, 60)
                lobe = next(k for k, comps in KC_LOBES.items() if target in comps)
                connect(da[t], kcs[lobe], 5, 8, p=0.1)
            else:
                connect(da[t], background[target], 5, 25, p=0.3)

    # MBONs send their output to superior neuropils, lateral horn and central complex.
    downstream = np.concatenate([background["SMP_R"], background["SIP_R"], background["LH_R"], background["FB_R"]])
    for m in mbons.values():
        connect(m, downstream, 5, 30, p=0.08)

    # Background wiring: dense within a neuropil, sparse between neuropils.
    all_bg = np.concatenate(list(background.values()))
    for members in background.values():
        connect(members, members, 5, 20, p=0.06)
    connect(all_bg, all_bg, 5, 15, p=0.004)
    # A little feedback onto DA neurons, so the DA pool is not purely a source.
    connect(rng.choice(all_bg, 60, replace=False), np.concatenate(list(da.values())), 5, 15, p=0.2)

    pre, post = zip(*edges)
    W = sp.csr_matrix((list(edges.values()), (pre, post)), shape=(n, n), dtype=float)
    neurons = pd.DataFrame(rows)
    regions = regions_table()
    neurons["super_region"] = neurons["region"].map(lambda r: regions.get(r, {}).get("super_region"))
    return build_connectome(W, neurons, ROOT_ID_BASE + np.arange(n), regions)


def _region(target: str) -> str:
    return COMPARTMENTS.get(target, target)
