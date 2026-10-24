"""Every tunable number in neuroSim lives here, with the reason for its default.

Change a value here, never inline. The UI shows these as "model assumptions",
and the sensitivity check (docs/ENGINE_DESIGN.md, section 9) sweeps them.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
# Secrets such as GEMINI_API_KEY live in a gitignored .env at the repo root
# (copy .env.example). Variables already set in the shell win over the file.
load_dotenv(ROOT / ".env")

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
EVIDENCE_PATH = ROOT / "data" / "evidence.json"
# Rows Bio approved from paper uploads (agent/papers.py). Kept apart from the
# hand-curated table so a live approval never rewrites evidence.json.
APPROVED_EVIDENCE_PATH = ROOT / "data" / "evidence_approved.json"
# Paper rows waiting for Bio's decision, so an API reload doesn't drop them (gitignored).
PROPOSALS_PATH = ROOT / "data" / "evidence_proposals.json"

# Serve api/mocks.py payloads instead of the engine until the engine works.
# The API and the agent's tools both read this, so they always agree.
USE_MOCKS = os.environ.get("NEUROSIM_MOCKS", "1") == "1"

# --- Graph construction (CS1) -------------------------------------------------

# Drop neuron pairs with fewer synapses than this. 5 is the convention used in
# FlyWire papers: below it, a large share of connections are detection errors.
SYNAPSE_THRESHOLD = 5

# --- Propagation (CS1) ----------------------------------------------------------

# How many synaptic steps away from the seeds we follow. 3 reaches most of the
# brain-scale effect while staying explainable ("up to 3 steps downstream").
HOPS = 3

# Each further step counts this much less than the previous one.
# 0.5 means step 2 counts half as much as step 1, step 3 a quarter.
DECAY = 0.5

# --- Vulnerability scoring (CS1) -----------------------------------------------

# Groups (brain regions / cell types) with fewer neurons than this are not
# ranked: their mean impact is too noisy to compare.
MIN_GROUP_SIZE = 5

# A neuron counts as "strongly hit" when its direct dependency is at least this.
# 0.10 = at least 10% of its input came from the seeds.
STRONG_HIT = 0.10

# --- Random baseline (CS1) -------------------------------------------------------

N_RANDOM_DRAWS = 200      # enough for stable z-scores; ~seconds with batching
RANDOM_SEED = 42          # fixed so every run is reproducible
FDR_ALPHA = 0.05          # Benjamini-Hochberg threshold for "above chance"

# --- Confidence (Bio) ------------------------------------------------------------

EVIDENCE_TIER_WEIGHT = {"high": 0.9, "medium": 0.7, "low": 0.4}
TYPE_MATCH_WEIGHT = {"exact": 1.0, "inferred": 0.6}
# Ortholog confidence = DIOPT score / this. 18 is a placeholder: set it to the
# maximum score of the DIOPT version Bio used for data/evidence.json.
DIOPT_MAX_SCORE = 18
# Used while an ortholog's DIOPT score is still blank in evidence.json, so
# seeds are not zeroed out by a missing number. Shown in the mapping chain.
UNSCORED_ORTHOLOG_CONFIDENCE = 0.5

# --- Drawing (CS1 -> CS2) ----------------------------------------------------------

SUBGRAPH_MAX_NODES = 200

# --- Agent (CS2) -------------------------------------------------------------------

# Which model family answers the agent, the run summary and paper extraction:
# "gemma" (open Gemma 4 models, served free by the Gemini API with the same
# GEMINI_API_KEY; the hackathon's "Best use of Gemma" track) or "gemini".
# Restart the API after changing it.
LLM = os.environ.get("NEUROSIM_LLM", "gemini").strip().lower()
if LLM not in ("gemma", "gemini"):
    raise ValueError(f"NEUROSIM_LLM must be gemma or gemini, not {LLM!r}.")
LLM_NAME = LLM.capitalize()   # shown in error messages and the UI

if LLM == "gemma":
    # Gemma goes through generate_content (agent/gemma.py), the API Google
    # documents for it. Measured live on the free tier (2026-10-24): the 26B
    # MoE (4B active) answers in seconds and called the right tools; 31B dense
    # took 20-30s just to say hi. Each has its own free quota.
    AGENT_MODEL = "gemma-4-26b-a4b-it"
    AGENT_FALLBACK_MODEL = "gemma-4-31b-it"
else:
    # Gemini via the Interactions API. Flash is fast and cheap enough for a live demo.
    AGENT_MODEL = "gemini-3.8-flash"
    # Free-tier fallback when AGENT_MODEL returns 429 (rate limit). gemini-4-argon
    # is not on the free tier, so never set it here.
    AGENT_FALLBACK_MODEL = "gemini-3.5-flash-lite"
# "low" | "medium" | "high". Pick the lowest that still gives good answers.
# Gemma thinks or doesn't: "medium" and "high" turn it on, "low" turns it off.
# Thinking made Gemma chat turns take over a minute, so it is off there.
AGENT_THINKING_LEVEL = "low" if LLM == "gemma" else "medium"
# Caps thinking AND the answer together, so keep it generous.
AGENT_MAX_OUTPUT_TOKENS = 16000
# Tool rounds per user turn before we stop and answer with what we have.
# A full "compare two genes" turn takes 4 (two chains, two runs, one compare).
AGENT_MAX_TOOL_ROUNDS = 8
# On a 429 we wait what the API suggests, but never longer than this, then
# retry once before switching to AGENT_FALLBACK_MODEL.
AGENT_RETRY_MAX_WAIT_S = 20
# Per-request timeout. When the model is overloaded it can hang or return
# 503/504; either way we move to the fallback instead of leaving the user
# waiting. The API also gets it as its own deadline (a 504 when it runs out).
# Gemma on the free tier is slower than Flash, so it gets longer.
AGENT_REQUEST_TIMEOUT_S = 60 if LLM == "gemma" else 30
# After a switch to the fallback, stay on it this long before trying Flash again.
AGENT_FALLBACK_COOLDOWN_S = 300
# A whole agent turn (every Gemini call and tool round) stops after this and
# answers with a readable 503. Keep it well under the frontend proxy's 300s
# timeout (frontend/next.config.ts), or the user gets the proxy's bare 500.
AGENT_TURN_DEADLINE_S = float(os.environ.get("NEUROSIM_AGENT_TURN_DEADLINE_S", "180" if LLM == "gemma" else "120"))

# Paper upload: PDFs larger than this are refused before they reach Gemini.
PAPER_MAX_BYTES = 20 * 1024 * 1024
# Reading a whole paper takes longer than an agent step.
PAPER_TIMEOUT_S = 150
# The whole extraction (Flash, then the fallback if Flash times out) stops
# after this. Two full PAPER_TIMEOUT_S calls would reach the frontend proxy's
# 300s timeout, so the fallback only gets what is left.
PAPER_DEADLINE_S = 240
# A paper's text is cut to this many characters after the reference list is
# dropped; methods, results and legends fit well within it. About 50k tokens
# for Gemini; about 15k for Gemma, so one paper fits Gemma's free-tier
# tokens-per-minute limit with room for the answer.
PAPER_MAX_CHARS = 60_000 if LLM == "gemma" else 200_000
