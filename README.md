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
  prep/download_labels.py  fetch FlyWire cell type / region / NT labels into data/raw/
  bio/evidence.py      gene -> ortholog -> clusters -> seed neurons        (Bio + CS1)
  bio/expression.py    atlas TPM for a gene's fly genes, shown on the seeds (annotation only)
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
  agent/papers.py      paper PDF/text/DOI -> checked evidence rows for Bio (CS2)
  agent/prompts.py     system prompt rules                                 (Bio)
data/
  raw/                 downloads go here (not committed)
  processed/           output of prep (not committed; regenerate)
  evidence.json        hand-curated evidence table: orthologs, evidence rows, clusters,
                       and the expression atlas's PAM crosswalk (committed)
  expression_table.csv Kait's expression atlas (Davis et al. 2020, PAM only; committed)
  evidence_approved.json  rows approved from paper uploads (written by the app; not committed yet)
  evidence_proposals.json paper rows waiting for review (written by the app; gitignored)
docs/ENGINE_DESIGN.md  how the simulation and vulnerability model work, and why
frontend/               Next.js workspace app (CS2); SCREENS.md maps each view to its endpoint
tests/test_engine_toy.py  6-neuron toy graph with hand-checked answers
```

## Data to download (before the event)

1. FlyWire FAFB v783 connections: `proofread_connections_783.feather` (852 MB)
   from https://zenodo.org/records/10676866 → `data/raw/`
2. Neuron labels: `python -m neurosim.prep.download_labels` (run from
   `backend/`) fetches them into `data/raw/` and checks each file's checksum.
   No login needed. It writes `data/raw/labels_manifest.json` with the URL,
   size and SHA-256 of every file.
   - `flywire_neuron_annotations_783.tsv`: cell type, super class, side and
     predicted neurotransmitter (`top_nt`) for all 139,248 neurons, from
     [flyconnectome/flywire_annotations](https://github.com/flyconnectome/flywire_annotations)
     tag `v3.2.0`.
   - `per_neuron_neuropil_count_{pre,post}_783.feather`: synapses per neuron
     per neuropil (region), from the same Zenodo record as step 1.

   On a fresh machine just run the script. If the annotations are already in
   place and only the Zenodo region files are missing (they weren't verified
   in the cloud, where Zenodo is blocked), run from the repo root:

   ```
   source .venv/bin/activate
   cd backend && python -m neurosim.prep.download_labels --only neuropil_pre neuropil_post
   ```

   It prints `verified md5` for each file and adds them to the manifest.

   Codex serves similar tables but needs a personal API token, so prep doesn't
   use it. All FlyWire data is CC BY 4.0: cite Dorkenwald et al. 2024 and
   Schlegel et al. 2024 (Nature), Eckstein et al. 2024 (Cell) for the
   neurotransmitter predictions, and Berg et al. 2026 (Cell) for the v3
   annotations.

## Running (once implemented)

```
pip install -r requirements.txt
python -m neurosim.prep.build_dataset            # once, ~minutes
cp .env.example .env                             # then paste your Gemini key into .env
(cd backend && uvicorn neurosim.api.main:app --reload \
  --reload-dir neurosim --reload-exclude 'neurosim/prep/*')  # API on :8000
pytest tests/                                    # engine, pipeline and API tests
cd backend && python -m neurosim.engine.validation   # PAM -> mushroom body check
cd frontend && npm install && npm run dev        # app on :3000 (see frontend/SCREENS.md)
```

`--reload-exclude` keeps edits to `prep/` (the dataset build) from restarting
the API mid-request; every other file under `neurosim/`, `config.py` and
`models.py` included, still reloads it. The exclude needs `watchfiles`, which
is in requirements.txt (plain `uvicorn` ignores the flag without it).

The API picks its data source at startup: the real pipeline when
`data/processed/` exists and the engine is implemented, otherwise mocks.
`NEUROSIM_MOCKS=1` or `=0` forces either. Mock runs still take their seeds
and the gene list from the real evidence table when `data/processed/` exists;
only the engine's numbers are fake. `NEUROSIM_SYNTHETIC=1` runs the real engine on a small made-up brain
(`engine/synthetic.py`), so the full pipeline can be tried before prep has run.
Its numbers mean nothing biologically.

**Engine status.** The simulation math is CS1's to write and currently raises
`NotImplementedError`: `input_normalize` in `engine/graph.py`, and
`engine/perturb.py`, `propagate.py`, `vulnerability.py` and `baseline.py`.
Everything around it is in place (pipeline, seed resolution, Sankey/subgraph,
comparison, validation script, API), and the tests marked `needs_engine` are
expected to fail until the math exists. The API stays on mocks until then.

## Evidence from papers

The "Evidence from a paper" panel (left column) adds rows to the evidence
table from a paper, so a new finding seeds the next run:

1. Drop a PDF, paste the text, or give a DOI or PubMed ID. A DOI only gives
   the full text when the paper is open access on Europe PMC; otherwise the
   model sees just the abstract, which rarely names clusters, so prefer the
   PDF.
2. The model proposes rows (gene, fly gene, model, clusters lost, tier,
   finding) with a verbatim quote. Each row shows its checks: clusters mapped
   to the table, quote found on which page, problems in plain words (unknown
   gene or cluster, a cluster the quote doesn't name, already in the table,
   read by the backup model), and the confidence its seeds would get.
3. Edit a row if needed, then Approve or Reject it. Approved rows go to
   `data/evidence_approved.json`, are listed under the panel with a remove
   button, and are used by the next run of that gene. The mapping chain and
   the Overview mark them "uploaded paper".

A good test paper is Yang et al. 2006, PNAS
([doi:10.1073/pnas.0602493103](https://doi.org/10.1073/pnas.0602493103)):
it should give PINK1 → Pink1, RNAi, PPL1 lost, tier high. Wang et al. 2006
(PMC1569195) comes back flagged as already in the table. PDFs need `pypdf`
(in requirements.txt). How the pipeline works and how confidence is computed:
`docs/ENGINE_DESIGN.md`, section 1b.

**Which model reads papers.** The agent, run summaries and paper extraction
share one client (`agent/gemini.py`) and the free-tier guards in
`config.py`; paper extraction calls the model in one place,
`papers.ask_model`. On this branch that is Gemini (`gemini-3.8-flash`,
falling back to `gemini-3.5-flash-lite`). The `gemma` branch makes Gemma 4
the default for all three and keeps Gemini selectable with
`NEUROSIM_LLM=gemini`; both use the same `GEMINI_API_KEY`.
