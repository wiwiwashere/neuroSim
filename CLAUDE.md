# neuroSim

## Overview

neuroSim is a Parkinson's disease circuit simulator for the Drosophila brain. Given a human gene (e.g. PINK1), it identifies the fly dopamine neurons that published studies show degenerate, traces their connections through the FlyWire connectome (~139k neurons), and ranks which brain regions lose unusual input. A Three.js 3D visualiser shows the connectome lighting up and fading over simulated degeneration time, driven by neurolib neural mass dynamics.

## Stack

Backend: Python 3.11+, FastAPI, scipy sparse matrices, neurolib (WCModel by default; ALN is slower)

Frontend: Next.js 15, React 19, TypeScript, Three.js via @react-three/fiber

Data: FlyWire FAFB v783 connectome (Zenodo), hand-curated evidence table

## Commands

- Install backend: `pip install -r requirements.txt` (from repo root)
- Install frontend: `cd frontend && pnpm install`
- Run backend: `cd backend && uvicorn neurosim.api.main:app --reload --reload-dir neurosim --reload-exclude 'neurosim/prep/*'`
- Run frontend: `cd frontend && pnpm dev`
- Test: `pytest tests/`
- Typecheck frontend: `cd frontend && pnpm typecheck`
- Lint frontend: `cd frontend && pnpm lint`
- Build dataset (once): `cd backend && python -m neurosim.prep.build_dataset`

## Layout

- `backend/neurosim/engine/` — simulation math (graph, perturb, propagate, vulnerability, baseline, degeneration)
- `backend/neurosim/bio/` — gene → fly ortholog → seed neurons
- `backend/neurosim/api/` — FastAPI endpoints + mock data
- `backend/neurosim/agent/` — Gemma/Gemini LLM agent
- `frontend/src/components/charts/` — all data-vis: network-3d.tsx (Three.js), network.tsx (Cytoscape 2D), damage-flow.tsx, ranked-bars.tsx
- `frontend/src/components/workspace/` — workspace panels (results, perturbation, gene-picker, agent-panel)
- `data/evidence.json` — hand-curated evidence table (committed)
- `docs/ENGINE_DESIGN.md` — full simulation design spec

## Key env vars

- `GEMINI_API_KEY` — required for the LLM agent
- `NEUROSIM_MOCKS=1` — force mock data (no engine needed)
- `NEUROSIM_SYNTHETIC=1` — run real engine on a synthetic toy brain
- `NEUROSIM_LLM=gemini` — use Gemini Flash instead of Gemma

## Conventions

- Keep changes small and focused; one logical change per commit.
- Add or update tests alongside code changes.
- Don't commit secrets, large datasets, or generated outputs; put them in `.gitignore`.
- Engine stubs raise `NotImplementedError`; the API falls back to mocks automatically.
- Three.js components must be imported with `dynamic(..., { ssr: false })` — no server rendering.
- neurolib runs CPU-bound in a thread via `run_in_threadpool`. If neurolib is missing, degeneration uses a numpy Wilson–Cowan integrator with the same contract.
- Degeneration coupling is built from subgraph region↔region weights (same labels as `GraphNode.group`); Sankey inflows are the fallback. Time series is 60 frames (~6 fps over 10 s wall-clock). `per_hop` is merged onto graph nodes on the frontend from `result.top_neurons`.
- Ask before pushing, force-pushing, or rewriting history.
