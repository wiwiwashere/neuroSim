"""Vercel ASGI entry point for the existing neuroSim FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent if (PROJECT_ROOT.parent / "backend").is_dir() else PROJECT_ROOT
sys.path.insert(0, str(REPO_ROOT / "backend"))

from neurosim.api.vercel import app  # noqa: E402,F401
