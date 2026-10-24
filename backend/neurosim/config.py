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

# --- Drawing (CS1 -> CS2) ----------------------------------------------------------

SUBGRAPH_MAX_NODES = 200

# --- Agent (CS2) -------------------------------------------------------------------

# Gemini via the Interactions API. Flash is fast and cheap enough for a live demo.
AGENT_MODEL = "gemini-3.8-flash"
# Free-tier fallback when AGENT_MODEL returns 429 (rate limit). gemini-4-argon
# is not on the free tier, so never set it here.
AGENT_FALLBACK_MODEL = "gemini-3.5-flash-lite"
# "low" | "medium" | "high". Pick the lowest that still gives good answers.
AGENT_THINKING_LEVEL = "medium"
# Caps thinking AND the answer together, so keep it generous.
AGENT_MAX_OUTPUT_TOKENS = 16000
# Tool rounds per user turn before we stop and answer with what we have.
# A full "compare two genes" turn takes 4 (two chains, two runs, one compare).
AGENT_MAX_TOOL_ROUNDS = 8
# On a 429 we wait what the API suggests, but never longer than this, then
# retry once before switching to AGENT_FALLBACK_MODEL.
AGENT_RETRY_MAX_WAIT_S = 20
# Per-request timeout. When Flash is overloaded it can hang or return 503;
# either way we move to the fallback instead of leaving the user waiting.
AGENT_REQUEST_TIMEOUT_S = 30
# After a switch to the fallback, stay on it this long before trying Flash again.
AGENT_FALLBACK_COOLDOWN_S = 300
# A whole agent turn (every Gemini call and tool round) stops after this and
# answers with a readable 503. Keep it well under the frontend proxy's 300s
# timeout (frontend/next.config.ts), or the user gets the proxy's bare 500.
AGENT_TURN_DEADLINE_S = float(os.environ.get("NEUROSIM_AGENT_TURN_DEADLINE_S", "120"))

# Paper upload: PDFs larger than this are refused before they reach Gemini.
PAPER_MAX_BYTES = 20 * 1024 * 1024
# Reading a whole paper takes longer than an agent step.
PAPER_TIMEOUT_S = 150
