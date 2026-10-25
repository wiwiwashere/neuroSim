# neuroSim

## Overview

neuroSim is a disease circuit simulator for the Drosophila brain. Given a human gene (e.g. PINK1), it identifies the fly neurons that published studies show degenerate, traces their connections through the FlyWire connectome (~139k neurons), and ranks which brain regions and cell types lose unusual input compared with random dopamine neurons. Parkinson's is built in; users can add other diseases as a table of genes and affected neurons. A Three.js 3D view shows the connectome fading over simulated degeneration time, driven by neurolib neural mass dynamics. The agent, run summary and paper upload use Gemma 4 (Gemini API free tier).

## Stack

Backend: Python 3.11+, FastAPI, scipy sparse matrices, neurolib (WCModel by default; ALN is slower)

Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS 4 + shadcn/ui, TanStack Query, Plotly, Cytoscape.js, Three.js via @react-three/fiber

Data: FlyWire FAFB v783 connectome (Zenodo), hand-curated evidence table

## Commands

- Install backend: `python -m pip install -r requirements.txt` (from repo root, venv active)
- Install frontend: `cd frontend && npm install`
- Run backend: `cd backend && python -m uvicorn neurosim.api.main:app --reload --reload-dir neurosim --reload-exclude 'neurosim/prep/*'`
- Run frontend: `cd frontend && npm run dev`
- Test: `python -m pytest tests/`
- Typecheck frontend: `cd frontend && npm run typecheck`
- Lint frontend: `cd frontend && npm run lint`
- Regenerate API types (API running): `cd frontend && npm run gen:api`
- Build dataset (once): `cd backend && python -m neurosim.prep.build_dataset`
- Validate the engine: `cd backend && python -m neurosim.engine.validation` (add `--synthetic` without data)

## Layout

- `backend/neurosim/engine/` — simulation math (graph, perturb, propagate, vulnerability, baseline, degeneration); `pipeline.py` is the only entry point the API and agent call
- `backend/neurosim/bio/` — gene → fly ortholog → seed neurons; expression, direct targets, user-supplied diseases
- `backend/neurosim/api/` — FastAPI endpoints + sample payloads (`mocks.py`) for when there is no connectome data
- `backend/neurosim/agent/` — Gemma/Gemini LLM agent, run summary, paper extraction
- `frontend/src/components/charts/` — all data-vis: network-3d.tsx (Three.js), network.tsx (Cytoscape 2D), damage-flow.tsx, ranked-bars.tsx
- `frontend/src/components/workspace/` — workspace panels (results, perturbation, gene-picker, agent-panel, custom-disease, paper-evidence)
- `data/evidence.json` — hand-curated evidence table (committed)
- `docs/ENGINE_DESIGN.md` — full simulation design spec
- `frontend/SCREENS.md` — every view and the endpoint behind it

## Key env vars

- `GEMINI_API_KEY` — required for the LLM agent (serves Gemma and Gemini)
- `NEUROSIM_LLM=gemini` — use Gemini Flash instead of Gemma (default `gemma`)
- `NEUROSIM_MOCKS=1` / `=0` — force sample payloads / the real engine (default: real engine when `data/processed/` exists)
- `NEUROSIM_SYNTHETIC=1` — run the real engine on a synthetic toy brain

## Conventions

- Keep changes small and focused; one logical change per commit.
- Add or update tests alongside code changes.
- Don't commit secrets, large datasets, or generated outputs; put them in `.gitignore`.
- Use npm, not pnpm (the repo's lock file is `package-lock.json`).
- The API serves the real engine when `data/processed/` exists and `pipeline.engine_ready()` is true, otherwise the sample payloads in `api/mocks.py` (run IDs start with `mock-`).
- Three.js components must be imported with `dynamic(..., { ssr: false })` — no server rendering.
- neurolib runs CPU-bound in a thread via `run_in_threadpool`. If neurolib is missing, degeneration uses a numpy Wilson–Cowan integrator with the same contract.
- Degeneration coupling is built from subgraph region↔region weights (same labels as `GraphNode.group`); Sankey inflows are the fallback. Time series is 60 frames (~6 fps over 10 s wall-clock). `per_hop` is merged onto graph nodes on the frontend from `result.top_neurons`.
- Ask before pushing, force-pushing, or rewriting history.
