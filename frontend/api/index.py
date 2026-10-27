"""Vercel ASGI entry point for the existing neuroSim FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from neurosim.api.vercel import app  # noqa: E402,F401
