"""Download the FlyWire v783 neuron labels into data/raw/ (not committed).

Run once:  python -m neurosim.prep.download_labels
           python -m neurosim.prep.download_labels --only annotations

Every source is public and needs no login:

    annotations   Supplemental_file1_neuron_annotations.tsv from
        github.com/flyconnectome/flywire_annotations, pinned to tag v3.2.0
        (the 783 materialization). One row per neuron (139,248): root_id,
        super_class, cell_class, cell_type, hemibrain_type, side, top_nt
        (predicted neurotransmitter: acetylcholine, gaba, glutamate, dopamine,
        serotonin, octopamine), top_nt_conf, known_nt. Checked against a
        SHA-256 recorded here.
    neuropil_pre / neuropil_post   per_neuron_neuropil_count_{pre,post}_783
        .feather from Zenodo record 10676866 (same record as the connections
        file): synapse counts per neuron per neuropil, outgoing and incoming.
        Checked against the MD5 Zenodo publishes for each file.

Codex (codex.flywire.ai) serves overlapping tables, but its downloads need a
personal API token, so the prep doesn't depend on it.

License: FlyWire data is CC BY 4.0. Cite Dorkenwald et al. 2024 and Schlegel et
al. 2024 (Nature) for the connectome and annotations, Eckstein et al. 2024
(Cell) for the neurotransmitter predictions, and Berg et al. 2026 (Cell) for
the v3 annotation updates.

Each run writes data/raw/labels_manifest.json: source URL, size, SHA-256 and
download time for every file, so a teammate can check they have the same data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from neurosim import config

ANNOTATIONS_TAG = "v3.2.0"
ZENODO_RECORD = "10676866"

SOURCES = {
    "annotations": {
        "file": "flywire_neuron_annotations_783.tsv",
        "url": (
            "https://raw.githubusercontent.com/flyconnectome/flywire_annotations/"
            f"{ANNOTATIONS_TAG}/supplemental_files/Supplemental_file1_neuron_annotations.tsv"
        ),
        "sha256": "b214970b55d2fbe0853bba536fdcb9e28730f4eb7ab06f600491df795da683cd",
    },
    "neuropil_pre": {
        "file": "per_neuron_neuropil_count_pre_783.feather",
        "zenodo_key": "per_neuron_neuropil_count_pre_783.feather",
    },
    "neuropil_post": {
        "file": "per_neuron_neuropil_count_post_783.feather",
        "zenodo_key": "per_neuron_neuropil_count_post_783.feather",
    },
}

MANIFEST = "labels_manifest.json"
CHUNK = 1 << 20


def file_hash(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def zenodo_files() -> dict[str, dict]:
    """File key -> {url, md5} for the Zenodo record, from its public API."""
    with urllib.request.urlopen(f"https://zenodo.org/api/records/{ZENODO_RECORD}", timeout=60) as r:
        record = json.load(r)
    out = {}
    for f in record["files"]:
        algo, _, digest = f["checksum"].partition(":")
        out[f["key"]] = {"url": f["links"]["self"], algo: digest}
    return out


def download(url: str, dest: Path) -> None:
    """Stream url to dest via a .part file, so an interrupted run leaves no
    half file under the real name."""
    part = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, part.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(CHUNK):
            f.write(chunk)
            done += len(chunk)
            if total and sys.stdout.isatty():
                print(f"\r  {done / total:6.1%} of {total / 1e6:.1f} MB", end="", flush=True)
    print(f"\r  {done / 1e6:.1f} MB")
    part.replace(dest)


def fetch(name: str, src: dict, force: bool) -> dict:
    """Download one source if needed and verify it. Returns its manifest entry."""
    dest = config.RAW_DIR / src["file"]
    url, expected = src.get("url"), {}
    if "sha256" in src:
        expected["sha256"] = src["sha256"]
    if "zenodo_key" in src:
        z = zenodo_files()[src["zenodo_key"]]
        url = z.pop("url")
        expected.update(z)

    if dest.exists() and not force and all(file_hash(dest, a) == d for a, d in expected.items()):
        print(f"{name}: {dest.name} already present and verified")
    else:
        print(f"{name}: downloading {url}")
        download(url, dest)
        for algo, digest in expected.items():
            got = file_hash(dest, algo)
            if got != digest:
                bad = dest.with_name(dest.name + ".bad")
                shutil.move(dest, bad)
                raise SystemExit(f"{name}: {algo} mismatch (got {got}, expected {digest}); kept as {bad.name}")
        print(f"{name}: verified {', '.join(expected) or 'nothing (no checksum known)'}")

    return {
        "file": dest.name,
        "url": url,
        "bytes": dest.stat().st_size,
        "sha256": file_hash(dest, "sha256"),
        "downloaded_at": datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", nargs="+", choices=SOURCES, help="download just these sources")
    parser.add_argument("--force", action="store_true", help="download again even if verified")
    args = parser.parse_args(argv)

    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = config.RAW_DIR / MANIFEST
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    failed = []
    for name in args.only or SOURCES:
        try:
            manifest[name] = fetch(name, SOURCES[name], args.force)
        except urllib.error.URLError as e:
            print(f"{name}: could not reach the source ({e.reason})", file=sys.stderr)
            failed.append(name)
            continue
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest: {manifest_path}")
    if failed:
        raise SystemExit(f"not downloaded: {', '.join(failed)}. Check the network and run again.")


if __name__ == "__main__":
    main(sys.argv[1:])
