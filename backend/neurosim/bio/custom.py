"""User-supplied diseases (CS2): rows someone uploads or types in, checked like
paper rows, saved beside the evidence table, never reviewed by Bio.

The built-in pipeline is data-driven: disease -> genes -> ortholog -> evidence
rows naming the fly neurons lost -> seeds. Nothing here changes that chain; it
only adds rows to it. A user row says: in this disease, this human gene (with
this fly ortholog if our table lacks it) affects these fly neurons, named as
dopamine clusters from the cluster table (PPL1, PAM, PPM3...) or as FlyWire
v783 cell types (MBON01, KCg-m...). A cell type becomes a one-type cluster in
the merged table (bio/evidence.load_evidence), so the chain, the mocks and the
engine need no special case.

Every row is checked before it is saved (check_row): ortholog known or
supplied, every affected name resolved with its neuron count, duplicates,
confidence, and a note when the seeds are not dopamine neurons, because the
engine's random baseline draws dopamine neurons (engine/baseline.py, CS1's
call whether that pool should follow the seeds).

Saved diseases live in config.CUSTOM_DISEASES_PATH (gitignored) and show up in
the picker with a "your data" tag. The UI, the chain and the Overview label
their rows "user-supplied, not reviewed by Bio".
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from neurosim import config
from neurosim.bio import evidence

ROW_FIELDS = ["disease", "human_gene", "fly_gene", "affected", "model_type", "finding", "citation", "url", "tier"]
# Column names people are likely to use, mapped to ours.
COLUMN_ALIASES = {
    "gene": "human_gene", "human gene": "human_gene", "symbol": "human_gene",
    "fly": "fly_gene", "fly ortholog": "fly_gene", "ortholog": "fly_gene", "fly gene": "fly_gene",
    "clusters": "affected", "cell_types": "affected", "cell types": "affected", "neurons": "affected",
    "affected neurons": "affected", "lost": "affected",
    "model": "model_type", "model type": "model_type",
    "source": "citation", "paper": "citation", "reference": "citation",
    "link": "url", "doi": "url",
    "confidence": "tier", "evidence": "tier",
    "note": "finding", "notes": "finding", "description": "finding",
}
MODEL_TYPES = ["mutant", "RNAi", "overexpression", "other"]
MAX_ROWS = 50
MAX_BYTES = 2 * 1024 * 1024
SEPARATORS = re.compile(r"[;|]")

TEMPLATE_ROWS = [
    {"disease": "Huntington's disease", "human_gene": "HTT", "fly_gene": "htt", "affected": "PAM; MBON01",
     "model_type": "overexpression", "finding": "Expanded-repeat HTT expressed in dopamine neurons caused PAM loss.",
     "citation": "Your source, e.g. Smith et al. 2020, J Neurosci", "url": "https://doi.org/...", "tier": "medium"},
    {"disease": "Huntington's disease", "human_gene": "HTT", "fly_gene": "htt", "affected": "KCg-m",
     "model_type": "other", "finding": "Replace this row with your own, or delete it.", "citation": "", "url": "", "tier": "low"},
]
FIELD_HELP = {
    "disease": "Disease name, the same on every row (Huntington's disease).",
    "human_gene": "Human gene symbol (HTT).",
    "fly_gene": "Fly ortholog symbol. Only needed when the gene isn't in neuroSim's ortholog table; otherwise the table's wins.",
    "affected": "Fly neurons lost or affected: dopamine clusters (PPL1, PPL2, PPM1/2, PPM3, PAL, PAM, ALL_DA) and/or FlyWire v783 cell types (MBON01, KCg-m), separated by ;",
    "model_type": "One of mutant, RNAi, overexpression, other. Optional.",
    "finding": "One plain sentence saying what was found. Optional.",
    "citation": "Where the finding comes from (paper, dataset, your own experiment). Optional.",
    "url": "Link to the source. Optional.",
    "tier": "high (counted with stats), medium (reported loss), low (indirect). Optional, defaults to medium.",
}


class CustomError(ValueError):
    """Bad input the user can fix; the message is shown as is."""


# --- Names -------------------------------------------------------------------------


def slug(name: str) -> str:
    """'Huntington's disease' -> 'huntingtons-disease'."""
    s = re.sub(r"['’]", "", name.strip().lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        raise CustomError("The disease needs a name.")
    return s


def _connectome_neurons():
    from neurosim.engine import graph

    if not graph.connectome_available():
        return None
    return graph.load_connectome().neurons


@lru_cache(maxsize=1)
def _catalogue_for(key: int) -> dict[str, dict]:
    neurons = _connectome_neurons()
    if neurons is None:
        return {}
    is_da = neurons["nt_type"].astype("string").str.lower().isin({"da", "dopamine"}).fillna(False)
    out: dict[str, dict] = {}
    for column in evidence.TYPE_COLUMNS:
        if column not in neurons:
            continue
        names = neurons[column].astype("string")
        frame = neurons.assign(_name=names.str.split("_").str[0], _da=is_da)
        frame = frame[frame["_name"].notna() & (frame["_name"] != "")]
        for name, group in frame.groupby("_name", sort=False):
            name = str(name)
            if name in out:
                continue
            out[name] = {"n_neurons": int(len(group)), "n_dopamine": int(group["_da"].sum()),
                         "super_class": str(group["super_class"].mode().iat[0]) if "super_class" in group else ""}
    return out


def cell_type_catalogue() -> dict[str, dict]:
    """FlyWire cell type -> {n_neurons, n_dopamine, super_class}, from the loaded
    connectome; empty when no connectome is on this machine (names then go unchecked)."""
    from neurosim.engine import graph

    conn = graph._CACHE
    return _catalogue_for(id(conn) if conn is not None else 0)


def clusters() -> dict[str, dict]:
    return {k: v for k, v in evidence.load_evidence().get("cluster_to_cell_types", {}).items()
            if not k.startswith("_") and not v.get("user_supplied")}


def resolve_name(name: str) -> dict:
    """What one affected name means: a dopamine cluster from the table, a
    FlyWire cell type, or nothing we know (with close matches to offer)."""
    from neurosim.agent.papers import normalize_clusters

    raw = name.strip()
    table = clusters()
    fixed = normalize_clusters([raw])[0] if raw else raw
    if fixed in table:
        cell_types = table[fixed].get("cell_types", [])
        return {"name": fixed, "kind": "cluster", "match": table[fixed].get("match", "inferred"),
                "n_cell_types": len(cell_types), "n_neurons": _cluster_size(fixed), "dopamine": True, "suggestions": []}
    catalogue = cell_type_catalogue()
    if not catalogue:
        return {"name": raw, "kind": "unchecked", "match": "exact", "n_cell_types": 1, "n_neurons": None,
                "dopamine": None, "suggestions": []}
    lower = {k.lower(): k for k in catalogue}
    hit = lower.get(raw.lower())
    if hit:
        info = catalogue[hit]
        return {"name": hit, "kind": "cell_type", "match": "exact", "n_cell_types": 1, "n_neurons": info["n_neurons"],
                "dopamine": info["n_dopamine"] * 2 >= info["n_neurons"], "suggestions": []}
    pool = list(table) + list(catalogue)
    close = difflib.get_close_matches(raw, pool, n=4, cutoff=0.75)
    # A name that is a prefix of real types (e.g. "MBON" or "PAM0") is worth suggesting too.
    prefix = [k for k in pool if k.lower().startswith(raw.lower())][:4] if len(raw) >= 3 else []
    return {"name": raw, "kind": "unknown", "match": None, "n_cell_types": 0, "n_neurons": 0, "dopamine": None,
            "suggestions": list(dict.fromkeys(close + prefix))[:5]}


def _cluster_size(cluster: str) -> int | None:
    neurons = _connectome_neurons()
    if neurons is None:
        return None
    _, cell_types = evidence.cluster_cell_types(cluster)
    if cell_types == [evidence.ALL_DA]:
        return int(neurons["nt_type"].astype("string").str.lower().isin({"da", "dopamine"}).fillna(False).sum())
    return int(evidence.type_mask(neurons, cell_types).sum())


def search_names(query: str, limit: int = 12) -> list[dict]:
    """Clusters and cell types matching a prefix, for the form's autocomplete."""
    q = query.strip().lower()
    out = []
    for name, entry in clusters().items():
        if q in name.lower():
            out.append({"name": name, "kind": "cluster", "n_neurons": _cluster_size(name), "dopamine": True})
    hits = []
    for name, info in cell_type_catalogue().items():
        if q and name.lower().startswith(q):
            hits.append((name, info))
    hits.sort(key=lambda h: (-h[1]["n_neurons"], h[0]))
    for name, info in hits:
        out.append({"name": name, "kind": "cell_type", "n_neurons": info["n_neurons"],
                    "dopamine": info["n_dopamine"] * 2 >= info["n_neurons"]})
    return out[:limit]


# --- Parsing ------------------------------------------------------------------------


def _split(value) -> list[str]:
    if isinstance(value, list):
        parts = [str(v) for v in value]
    else:
        parts = SEPARATORS.split(str(value or ""))
    return [p.strip() for p in parts if p and p.strip()]


def normalize_row(raw: dict) -> dict:
    """One row in our field names, trimmed, genes upper-cased, affected as a list."""
    row = {}
    for key, value in raw.items():
        k = str(key).strip().lower().replace("-", "_")
        k = COLUMN_ALIASES.get(k, k.replace(" ", "_"))
        if k in ROW_FIELDS and k not in row:
            row[k] = value
    out = {f: ("" if row.get(f) is None else row.get(f)) for f in ROW_FIELDS}
    out["disease"] = str(out["disease"]).strip()
    out["human_gene"] = str(out["human_gene"]).strip().upper()
    out["fly_gene"] = str(out["fly_gene"]).strip()
    out["affected"] = _split(out["affected"])
    model = str(out["model_type"]).strip()
    out["model_type"] = next((m for m in MODEL_TYPES if m.lower() == model.lower()), "other")
    out["finding"] = str(out["finding"]).strip()
    out["citation"] = str(out["citation"]).strip()
    out["url"] = str(out["url"]).strip()
    tier = str(out["tier"]).strip().lower()
    out["tier"] = tier if tier in config.EVIDENCE_TIER_WEIGHT else "medium"
    return out


def parse_upload(filename: str, data: bytes) -> list[dict]:
    """Rows from an uploaded CSV or JSON file (see template_csv / template_json)."""
    if len(data) > MAX_BYTES:
        raise CustomError(f"The file is over {MAX_BYTES // (1024 * 1024)} MB; a disease table should be a few rows.")
    text = data.decode("utf-8-sig", errors="replace").strip()
    if not text:
        raise CustomError("The file is empty.")
    name = (filename or "").lower()
    if name.endswith(".json") or text[0] in "[{":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as err:
            raise CustomError(f"That isn't valid JSON ({err.msg} at line {err.lineno}).") from err
        if isinstance(parsed, dict):
            rows = parsed.get("rows") or parsed.get("evidence") or []
            disease = parsed.get("disease") or parsed.get("name") or ""
            rows = [{"disease": disease, **r} if isinstance(r, dict) and not r.get("disease") else r for r in rows]
        else:
            rows = parsed
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise CustomError('JSON must be a list of rows, or {"disease": "...", "rows": [...]}.')
    else:
        sample = text[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not reader.fieldnames or not any(
            COLUMN_ALIASES.get(f.strip().lower(), f.strip().lower().replace(" ", "_")) in ROW_FIELDS for f in reader.fieldnames
        ):
            raise CustomError("The CSV needs a header row with at least human_gene and affected (download the template).")
        rows = [r for r in reader if any((v or "").strip() for v in r.values() if isinstance(v, str))]
    if not rows:
        raise CustomError("No rows in the file.")
    if len(rows) > MAX_ROWS:
        raise CustomError(f"At most {MAX_ROWS} rows per disease.")
    return [normalize_row(r) for r in rows]


def template_csv() -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=ROW_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(TEMPLATE_ROWS)
    return buf.getvalue()


def template_json() -> dict:
    rows = [{**r, "affected": _split(r["affected"])} for r in TEMPLATE_ROWS]
    for r in rows:
        r.pop("disease")
    return {"_fields": FIELD_HELP, "disease": TEMPLATE_ROWS[0]["disease"], "rows": rows}


# --- Checking ----------------------------------------------------------------------


def row_key(row: dict) -> tuple[str, frozenset[str]]:
    """(gene, resolved affected names): what makes two rows say the same thing."""
    return row["human_gene"], frozenset(resolve_name(n)["name"] for n in row["affected"])


def check_row(row: dict, disease_id: str, others: list[tuple] | None = None) -> dict:
    """What this row would do in a simulation, in plain terms. `others` are the
    row_keys of every row in the same upload, for duplicates within it."""
    table = evidence.load_evidence()
    problems: list[str] = []
    notes: list[str] = []
    gene = row["human_gene"]
    if not gene:
        problems.append("The row needs a human gene.")
    entry = table["orthologs"].get(gene) if gene else None
    if entry is not None and not entry.get("user_supplied"):
        orth = evidence.find_ortholog(gene)
        if not orth.fly_genes:
            problems.append(f"{gene} has no fly ortholog in neuroSim's table, so it can't be simulated.")
        elif row["fly_gene"] and row["fly_gene"].lower() not in {g.lower() for g in orth.fly_genes}:
            notes.append(f"neuroSim's table has {', '.join(orth.fly_genes)} as the fly ortholog of {gene}; "
                         f"it will be used instead of {row['fly_gene']}.")
        ortholog = {"known": True, "fly_genes": orth.fly_genes, "confidence": orth.confidence, "user_supplied": False}
    elif gene:
        if not row["fly_gene"]:
            problems.append(f"{gene} isn't in neuroSim's ortholog table, so give its fly ortholog in fly_gene.")
            ortholog = {"known": False, "fly_genes": [], "confidence": 0.0, "user_supplied": True}
        else:
            ortholog = {"known": False, "fly_genes": [row["fly_gene"]], "confidence": config.UNSCORED_ORTHOLOG_CONFIDENCE,
                        "user_supplied": True}
            notes.append(f"{gene} → {row['fly_gene']} is your ortholog call, not DIOPT's, so its confidence is "
                         f"{config.UNSCORED_ORTHOLOG_CONFIDENCE}.")
    else:
        ortholog = {"known": False, "fly_genes": [], "confidence": 0.0, "user_supplied": True}

    affected = [resolve_name(n) for n in row["affected"]]
    if not affected:
        problems.append("No affected neurons named, so this row seeds nothing.")
    for a in affected:
        if a["kind"] == "unknown":
            hint = f" Did you mean {', '.join(a['suggestions'])}?" if a["suggestions"] else ""
            problems.append(f"{a['name']} isn't a dopamine cluster or a FlyWire v783 cell type.{hint}")
        elif a["kind"] == "unchecked":
            notes.append(f"{a['name']} can't be checked against the connectome on this machine (data/processed is missing).")
        elif a["n_neurons"] == 0:
            problems.append(f"{a['name']} has no neurons in the connectome.")
        elif a["kind"] == "cell_type" and a["dopamine"] is False:
            notes.append(f"{a['name']} isn't a dopamine cell type. The engine compares every result against random "
                         "dopamine neurons, so read its baseline with care.")
    names = [a["name"] for a in affected]
    if len(set(names)) < len(names):
        notes.append("The same name appears twice; it counts once.")

    seedable = [a for a in affected if a["kind"] in ("cluster", "cell_type", "unchecked")]
    confidence = None
    if ortholog["fly_genes"] and seedable:
        best = max(config.TYPE_MATCH_WEIGHT[a["match"]] for a in seedable)
        confidence = round(ortholog["confidence"] * config.EVIDENCE_TIER_WEIGHT[row["tier"]] * best, 3)

    key = (gene, frozenset(names))
    duplicate = any(
        r.disease == disease_id and r.human_gene == gene and frozenset(r.clusters) == frozenset(names)
        for r in table["evidence"]
        if not (r.user_supplied and r.user_supplied.disease_id == disease_id)
    )
    if duplicate:
        problems.append("Saved data for this disease already has this gene and these neurons.")
    if others is not None and others.count(key) > 1:
        problems.append("This gene and these neurons appear twice in the upload; keep one row.")
    return {"ortholog": ortholog, "affected": affected, "confidence": confidence, "can_seed": confidence is not None and not problems,
            "problems": problems, "notes": notes}


def preview(rows: list[dict], disease_name: str | None = None, filename: str = "typed in") -> dict:
    """Rows checked but not saved: {"disease": {id, name}, "rows": [row + checks], "ok", "problems"}."""
    rows = [normalize_row(r) for r in rows][:MAX_ROWS]
    names = [r["disease"] for r in rows if r["disease"]]
    name = (disease_name or "").strip() or (names[0] if names else "")
    problems: list[str] = []
    if not name:
        problems.append("Give the disease a name (the disease column, or the name field).")
        disease_id = ""
    else:
        disease_id = slug(name)
        if disease_id in builtin_diseases():
            problems.append(f"{name} is a built-in disease; pick another name (e.g. \"{name} (my data)\") to keep your rows apart.")
    if len({slug(n) for n in names}) > 1:
        problems.append(f"The rows name more than one disease ({', '.join(sorted(set(names)))}). Upload one disease at a time.")
    if not rows:
        problems.append("No rows.")
    keys = [row_key(r) for r in rows]
    checked = []
    for r in rows:
        r = {**r, "disease": name}
        r["checks"] = check_row(r, disease_id, keys)
        checked.append(r)
    ok = not problems and all(not r["checks"]["problems"] for r in checked)
    return {"disease": {"id": disease_id, "name": name}, "file": filename, "rows": checked, "ok": ok, "problems": problems}


def builtin_diseases() -> set[str]:
    return {row.disease for row in evidence.load_evidence()["evidence"] if not row.user_supplied}


# --- Saving --------------------------------------------------------------------------


def _read() -> dict:
    path = config.CUSTOM_DISEASES_PATH
    return json.loads(path.read_text()) if path.exists() else {"diseases": []}


def _write(data: dict) -> None:
    config.CUSTOM_DISEASES_PATH.write_text(json.dumps(data, indent=2) + "\n")


def save(rows: list[dict], disease_name: str | None = None, filename: str = "typed in") -> dict:
    """Check the rows and, if every one is fine, save the disease (replacing an
    earlier version with the same id). Returns the saved disease entry."""
    out = preview(rows, disease_name, filename)
    if not out["ok"]:
        bad = out["problems"] + [f"{r['human_gene'] or 'row'}: {p}" for r in out["rows"] for p in r["checks"]["problems"]]
        raise CustomError("Fix these first: " + " ".join(bad))
    disease_id, name = out["disease"]["id"], out["disease"]["name"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    orthologs: dict[str, dict] = {}
    evidence_rows = []
    for r in out["rows"]:
        checks = r["checks"]
        if checks["ortholog"]["user_supplied"]:
            orthologs[r["human_gene"]] = {"fly_genes": checks["ortholog"]["fly_genes"], "relationship": "user-supplied",
                                          "diopt_score": None, "diseases": [disease_id], "user_supplied": True}
        fly_gene = checks["ortholog"]["fly_genes"][0] if checks["ortholog"]["fly_genes"] else r["fly_gene"]
        names = list(dict.fromkeys(a["name"] for a in checks["affected"]))
        evidence_rows.append({
            "disease": disease_id,
            "human_gene": r["human_gene"],
            "fly_gene": fly_gene,
            "model_type": r["model_type"],
            "clusters": names,
            "finding": r["finding"] or f"User-supplied: {r['human_gene']} affects {', '.join(names)}.",
            "citation": r["citation"] or f"User-supplied ({filename})",
            "url": r["url"],
            "tier": r["tier"],
            "verified_by_bio": False,
            "user_supplied": {
                "id": uuid.uuid4().hex[:12],
                "disease_id": disease_id,
                "file": filename,
                "added_at": now,
                "cell_types": [a["name"] for a in checks["affected"] if a["kind"] in ("cell_type", "unchecked")],
                "non_dopamine": [a["name"] for a in checks["affected"] if a["kind"] == "cell_type" and a["dopamine"] is False],
            },
        })
    entry = {"id": disease_id, "name": name, "file": filename, "added_at": now, "n_rows": len(evidence_rows),
             "genes": sorted({r["human_gene"] for r in evidence_rows}), "orthologs": orthologs, "evidence": evidence_rows}
    data = _read()
    data["diseases"] = [d for d in data["diseases"] if d["id"] != disease_id] + [entry]
    _write(data)
    return summary(entry)


def summary(entry: dict) -> dict:
    """The entry without its rows' internals, for lists."""
    return {k: entry[k] for k in ("id", "name", "file", "added_at", "n_rows", "genes")} | {
        "rows": [{"human_gene": r["human_gene"], "fly_gene": r["fly_gene"], "affected": r["clusters"], "tier": r["tier"],
                  "finding": r["finding"], "citation": r["citation"], "url": r["url"], "model_type": r["model_type"],
                  "non_dopamine": r["user_supplied"]["non_dopamine"]} for r in entry["evidence"]]}


def list_custom() -> list[dict]:
    return [summary(d) for d in _read()["diseases"]]


def remove(disease_id: str) -> None:
    data = _read()
    kept = [d for d in data["diseases"] if d["id"] != disease_id]
    if len(kept) == len(data["diseases"]):
        raise KeyError(f"No user-supplied disease {disease_id}.")
    data["diseases"] = kept
    _write(data)


def custom_tables() -> list[dict]:
    """The saved entries as evidence.load_evidence wants them."""
    return _read()["diseases"]
