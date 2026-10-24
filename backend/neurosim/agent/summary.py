"""Structured run summary (CS2): Gemini fills a fixed JSON schema for one run,
and the UI renders it as a card.

Gemini only picks and explains. Every number on the card (z-scores, above
chance) is copied from the run afterwards, and circuits the run doesn't
contain are dropped, so the card can't show a number the engine didn't make.
"""

from __future__ import annotations

import json

from neurosim import config
from neurosim.agent import gemini
from neurosim.agent.tools import summarize_result
from neurosim.models import GroupLevel, SimulationResult

_LEVELS = [GroupLevel.SUPER_REGION.value, GroupLevel.REGION.value, GroupLevel.CELL_TYPE.value]

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One plain sentence: what this run shows, compared with chance."},
        "top_circuits": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "group": {"type": "string", "description": "Exact group name from the run's top_groups."},
                    "level": {"type": "string", "enum": _LEVELS},
                    "why": {"type": "string", "description": "One sentence on why it scores high, from the run data only."},
                },
                "required": ["group", "level", "why"],
            },
        },
        "caveats": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string"},
            "description": "Weak links in this run: low evidence tiers, inferred matches, sample data, what the measure misses.",
        },
        "next_experiment": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "The follow-up in a few words, e.g. 'PPL101 alone'."},
                "why": {"type": "string"},
                "human_gene": {"type": "string"},
                "mode": {"type": "string", "enum": ["knockout", "reduce_output"]},
                "strength": {"type": "number"},
                "seed_cell_types": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["description", "why", "human_gene", "mode"],
        },
    },
    "required": ["headline", "top_circuits", "caveats", "next_experiment"],
}

INSTRUCTION = """\
You summarise one neuroSim run for a results card. neuroSim measures
structural dependency in the adult fly connectome (FlyWire): how much of a
neuron's input comes from the perturbed seed neurons, compared with random
dopamine neurons. It does not predict symptoms, behaviour or anything in
humans; never say a fly or patient will do anything.

Use only the run data you are given. Name circuits exactly as they appear in
top_groups, prefer ones above chance, and do not write numbers in "why"
(the card shows the z-scores itself). If the data carries a note saying the
numbers are samples, the first caveat says so. Suggest one follow-up that the
tools can run: the same gene with reduce_output, one seed cell type alone, or
another gene for comparison.
"""

_CACHE: dict[str, dict] = {}


def _context(result: SimulationResult) -> str:
    data = summarize_result(result)
    if config.USE_MOCKS:
        data["note"] = "Sample numbers: the engine isn't built yet."
    data["evidence"] = [
        {"cell_type": t.cell_type, "match": t.match, "tiers": sorted({e.tier for e in t.evidence}),
         "verified_by_bio": all(e.verified_by_bio for e in t.evidence)}
        for t in result.seeds.seed_types
    ]
    return json.dumps(data, default=str)


def _ground(raw: dict, result: SimulationResult) -> dict:
    """Attach real numbers and drop anything the run doesn't contain."""
    by_name = {
        (level.value, g.group): g for level, groups in result.groups.items() for g in groups
    }
    circuits = []
    for c in raw.get("top_circuits", []):
        g = by_name.get((c.get("level"), c.get("group"))) or next(
            (g for (lvl, name), g in by_name.items() if name == c.get("group")), None
        )
        if g is None:
            continue
        circuits.append({
            "group": g.group, "level": g.level.value, "why": c.get("why", ""),
            "z_score": g.z_score, "above_chance": g.above_chance, "function_label": g.function_label,
        })

    nxt = raw.get("next_experiment") or {}
    request = None
    seed_types = {t.cell_type for t in result.seeds.seed_types}
    wanted = nxt.get("seed_cell_types") or None
    if nxt.get("human_gene") and nxt.get("mode") in ("knockout", "reduce_output"):
        same_gene = nxt["human_gene"].upper() == result.request.human_gene
        if not (wanted and same_gene and not set(wanted) <= seed_types):
            strength = nxt.get("strength")
            request = {
                "human_gene": nxt["human_gene"].upper(),
                "mode": nxt["mode"],
                "strength": min(1.0, max(0.0, float(strength))) if nxt["mode"] == "reduce_output" and strength is not None else 1.0,
                "seed_cell_types": wanted,
            }
    return {
        "run_id": result.run_id,
        "headline": raw.get("headline", ""),
        "top_circuits": circuits,
        "caveats": raw.get("caveats", [])[:3],
        "next_experiment": {"description": nxt.get("description", ""), "why": nxt.get("why", ""), "request": request},
    }


def summarize_run(result: SimulationResult) -> dict:
    if result.run_id in _CACHE:
        return _CACHE[result.run_id]
    state: dict = {}
    interaction = gemini.call(
        lambda model: gemini.client().interactions.create(
            model=model,
            input=_context(result),
            system_instruction=INSTRUCTION,
            response_format={"type": "text", "mime_type": "application/json", "schema": SCHEMA},
            generation_config={"thinking_level": "low", "max_output_tokens": 4000},
            store=False,
            timeout=config.AGENT_REQUEST_TIMEOUT_S,
        ),
        state,
    )
    try:
        raw = json.loads(interaction.output_text or "")
    except json.JSONDecodeError as err:
        raise gemini.GeminiUnavailable(f"Gemini returned a summary that isn't valid JSON: {err}") from err
    summary = {**_ground(raw, result), "model": state["model"]}
    _CACHE[result.run_id] = summary
    return summary
