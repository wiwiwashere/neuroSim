"""Vercel ASGI entry point for the existing neuroSim FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "backend" if (PROJECT_ROOT / "backend").is_dir() else PROJECT_ROOT.parent / "backend"
sys.path.insert(0, str(PACKAGE_ROOT))

from neurosim.api.vercel import app  # noqa: E402,F401
