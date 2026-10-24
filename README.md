# neuroSim — Disease Circuit Simulator (skeleton)

Give it a Parkinson's gene. It finds the fly neurons that published studies show
die when that gene is broken, traces where those neurons send their output in
the FlyWire connectome, and ranks which brain regions and cell types lose an
unusually large share of their input compared with chance.

This is a **skeleton**: every agreed feature exists as a stub function with a
docstring that says what it must do. Nothing computes yet. Engine stubs raise
`NotImplementedError`; the API serves mock data so the frontend can be built
on day one.

## Who owns what

| Owner | Folder | What |
| --- | --- | --- |
| Bio | `data/evidence.json`, `backend/neurosim/bio/`, `backend/neurosim/agent/prompts.py` | Gene → fly gene → dying DA clusters → connectome cell types, with citations and confidence. Agent rules and disclaimers. |
| CS1 | `backend/neurosim/prep/`, `backend/neurosim/engine/`, `tests/` | Data prep, graph, perturbation, propagation, vulnerability scoring, random baseline, subgraph, comparison. **Read `docs/ENGINE_DESIGN.md` first.** |
| CS2 | `backend/neurosim/api/`, `backend/neurosim/agent/`, `frontend/` | FastAPI, caching, the agent loop, all screens. |

## Layout

```
backend/neurosim/
  config.py            all tunable constants in one place (thresholds, decay, hops, ...)
  models.py            data contracts shared by engine, API, agent and frontend
  prep/build_dataset.py  offline: raw FlyWire files -> data/processed/*   (CS1)
  bio/evidence.py      gene -> ortholog -> clusters -> seed neurons        (Bio + CS1)
  engine/
    graph.py           load connectome, input-normalized weight matrix     (CS1)
    perturb.py         perturbation modes -> initial deficit vector        (CS1)
    propagate.py       multi-hop impact                                    (CS1)
    vulnerability.py   per-neuron -> per-group scores, disruption score    (CS1)
    baseline.py        random-seed null distribution, z-scores, p-values   (CS1)
    subgraph.py        small graph for drawing                             (CS1)
    compare.py         gene vs gene, leave-one-cluster-out                 (CS1)
    pipeline.py        one call that runs a whole experiment               (CS1)
  api/main.py          FastAPI endpoints                                   (CS2)
  api/mocks.py         fixed sample payloads until the engine works        (CS2)
  agent/tools.py       tools the LLM may call (thin wrappers on pipeline)  (CS2)
  agent/agent.py       the agent loop (Gemini API)                         (CS2)
  agent/gemini.py      Gemini client, rate-limit and overload fallback     (CS2)
  agent/summary.py     structured run summary card (Gemini, JSON schema)   (CS2)
  agent/papers.py      paper PDF -> proposed evidence rows for Bio         (CS2)
  agent/prompts.py     system prompt rules                                 (Bio)
data/
  raw/                 downloads go here (not committed)
  processed/           output of prep (not committed; regenerate)
  evidence.json        hand-curated evidence table (committed)
docs/ENGINE_DESIGN.md  how the simulation and vulnerability model work, and why
frontend/               Next.js workspace app (CS2); SCREENS.md maps each view to its endpoint
tests/test_engine_toy.py  6-neuron toy graph with hand-checked answers
```

## Data to download (before the event)

1. FlyWire FAFB v783 connections: `proofread_connections_783.feather` (852 MB)
   from https://zenodo.org/records/10676866 → `data/raw/`
2. Codex annotations (free Google sign-in + API token): the neuron
   classification, cell type and neurotransmitter CSVs → `data/raw/`
   (see the docstring in `prep/build_dataset.py` for which columns are used).

## Running (once implemented)

```
pip install -r requirements.txt
python -m neurosim.prep.build_dataset            # once, ~minutes
cp .env.example .env                             # then paste your Gemini key into .env
uvicorn neurosim.api.main:app --reload           # API on :8000
pytest tests/                                    # engine, pipeline and API tests
cd backend && python -m neurosim.engine.validation   # PAM -> mushroom body check
cd frontend && npm install && npm run dev        # app on :3000 (see frontend/SCREENS.md)
```

The API picks its data source at startup: the real pipeline when
`data/processed/` exists, otherwise mocks. `NEUROSIM_MOCKS=1` or `=0` forces
either. `NEUROSIM_SYNTHETIC=1` runs the real engine on a small made-up brain
(`engine/synthetic.py`), so the full pipeline can be tried before prep has run.
Its numbers mean nothing biologically.

**Engine status.** The simulation math is CS1's to write and currently raises
`NotImplementedError`: `input_normalize` in `engine/graph.py`, and
`engine/perturb.py`, `propagate.py`, `vulnerability.py` and `baseline.py`.
Everything around it is in place (pipeline, seed resolution, Sankey/subgraph,
comparison, validation script, API), and the tests marked `needs_engine` are
expected to fail until the math exists. The API stays on mocks until then.
