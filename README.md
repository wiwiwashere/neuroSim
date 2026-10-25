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

## Set up on your machine

Works on macOS and Windows. You need **Python 3.11+** (`python3 --version` on
macOS, `python --version` on Windows), **Node 18+** (`node --version`) and git.

Two habits prevent most setup problems:

- Activate the virtual environment in **every new terminal** before running
  any Python command. The prompt then starts with `(.venv)`.
- Always type `python -m pip` and `python -m uvicorn`, never bare `pip` or
  `uvicorn`. The bare commands can belong to a different Python, which installs
  packages where the app can't see them.

### 1. Python environment (from the repo root)

| | macOS (Terminal) | Windows (PowerShell) |
| --- | --- | --- |
| Create the venv (once) | `python3 -m venv .venv` | `python -m venv .venv` |
| Activate it (every terminal) | `source .venv/bin/activate` | `.venv\Scripts\activate` |
| Install packages | `python -m pip install -r requirements.txt` | `python -m pip install -r requirements.txt` |

On Windows, if PowerShell refuses to run the activate script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again. In
the old `cmd.exe` the activate command is `.venv\Scripts\activate.bat`.

Rerun the install line after pulling a change to `requirements.txt`. It
includes `neurolib`, which `engine/degeneration.py` uses for the 3D view's
degeneration time-series; if it won't install on your machine, that code
falls back to a plain numpy version.

### 2. API key

| macOS | Windows |
| --- | --- |
| `cp .env.example .env` | `copy .env.example .env` |

Open `.env` and paste the team's free-tier key after `GEMINI_API_KEY=` (ask
rafael for it in a direct message), or make your own free key at
https://aistudio.google.com/apikey. The same key serves Gemma and Gemini.
`.env` is gitignored: never commit it, paste it in a chat, or put it in code.
The key is only needed for the agent chat, the run summary and paper upload;
everything else works without it. Restart the API after editing `.env`.

### 3. Data (optional to run the app)

**You can skip this step.** Until `data/processed/` exists, the API serves
mock numbers, so every screen works on a fresh clone. The data is needed to
build `data/processed/` and run the real engine.

Everything in `data/raw/` and `data/processed/` is gitignored, so a fresh
clone has none of it and each person downloads their own copy:

| File in `data/raw/` | Size | How to get it |
| --- | --- | --- |
| `proofread_connections_783.feather` | 852 MB | Download by hand from [Zenodo record 10676866](https://zenodo.org/records/10676866) and move it into `data/raw/` |
| `flywire_neuron_annotations_783.tsv` | 32 MB | The download script below |
| `per_neuron_neuropil_count_pre_783.feather` and `per_neuron_neuropil_count_post_783.feather` | | The download script below (same Zenodo record) |

Then, with the venv active (same on macOS and Windows):

```
cd backend
python -m neurosim.prep.download_labels   # annotations + both region files, checksums verified
python -m neurosim.prep.build_dataset     # needs the connections file; writes data/processed/ in a few minutes
```

`build_dataset` needs the connections file and reads the annotations for cell
types; it doesn't read the two region files yet. More detail on each file is
in [Data to download](#data-to-download-before-the-event).

### 4. Run it

Use two terminals. In the first, with the venv active, start the API on :8000
(one line, same on macOS and Windows):

```
cd backend
python -m uvicorn neurosim.api.main:app --reload --reload-dir neurosim --reload-exclude "neurosim/prep/*"
```

In the second, start the app on :3000:

```
cd frontend
npm install    # first time, and after every pull that changes package.json
npm run dev
```

If you installed before the 3D view landed, run `npm install` again: it
added `three` and the `@react-three/*` packages. Use npm (the repo's
`package-lock.json`), not pnpm.

Open http://localhost:3000. The API's own docs are at
http://127.0.0.1:8000/docs. Run the tests from the repo root with
`python -m pytest tests/`; 23 of them are expected to show as `xfailed` until
the engine math exists (next section).

### For the engine owner (CS1)

- **Where the placeholders are.** The simulation math raises
  `NotImplementedError` in `input_normalize` in
  `backend/neurosim/engine/graph.py`, and in `engine/perturb.py`,
  `propagate.py`, `vulnerability.py` and `baseline.py`. Read
  `docs/ENGINE_DESIGN.md` first; every tunable constant is in
  `backend/neurosim/config.py`. `engine/degeneration.py` (the 3D view's
  Wilson–Cowan time-series) is separate and already runs.
- **The checklist.** The 23 tests marked `@needs_engine`
  (`tests/engine_status.py`) are the to-do list. `python -m pytest tests/ -rxX`
  lists them at the end. When one shows `XPASS`, your code makes it pass:
  remove its `@needs_engine` marker.
- **Try it before the data exists.** `python -m neurosim.engine.validation --synthetic`
  (from `backend/`) runs the PAM → mushroom body check on a small made-up
  brain. Starting the API with `NEUROSIM_SYNTHETIC=1` runs the whole app on
  that brain. Its numbers mean nothing biologically.
- **Switch the app to the real engine.** Build `data/processed/` (step 3),
  then start the API with `NEUROSIM_MOCKS=0`:
  - macOS: `NEUROSIM_MOCKS=0 python -m uvicorn neurosim.api.main:app --reload --reload-dir neurosim --reload-exclude "neurosim/prep/*"`
  - Windows (PowerShell): `$env:NEUROSIM_MOCKS="0"` first, then the usual uvicorn line in the same terminal.

  `python -m neurosim.engine.validation` without `--synthetic` runs the
  validation on the real data.

### Troubleshooting

- **`Address already in use`** (`[Errno 48]` on macOS, `[WinError 10048]` on
  Windows): an old API is still running on :8000. macOS:
  `lsof -ti :8000 | xargs kill`. Windows: `netstat -ano | findstr :8000`, then
  `taskkill /PID <the number in the last column> /F`. The same works for :3000;
  if 3000 is busy, `npm run dev` quietly moves to 3001, so check the URL it prints.
- **`ModuleNotFoundError: No module named 'google.genai'`** (or `fastapi`,
  `pyarrow`, ...): the venv isn't active, or pip installed somewhere else.
  Activate the venv and rerun `python -m pip install -r requirements.txt`.
  `python -c "import sys; print(sys.prefix)"` should print a path ending in `.venv`.
- **`No module named 'neurosim'`**: run backend commands from `backend/` (the
  tests run from the repo root).
- **`FileNotFoundError` mentioning `proofread_connections_783.feather`**:
  `build_dataset` can't find the connections file. Download it into
  `data/raw/` (step 3), or skip `build_dataset`: the app runs on mock numbers
  without it.
- **The chat panel says "Can't reach the neuroSim API on :8000"**: the API
  isn't running or crashed; look at its terminal.
- **The agent says the key was rejected**: `.env` is missing or the key is
  empty or wrong. Fix it and restart the API.

## Layout

```
backend/neurosim/
  config.py            all tunable constants in one place (thresholds, decay, hops, ...)
  models.py            data contracts shared by engine, API, agent and frontend
  prep/build_dataset.py  offline: raw FlyWire files -> data/processed/*   (CS1)
  prep/download_labels.py  fetch FlyWire cell type / region / NT labels into data/raw/
  bio/evidence.py      gene -> ortholog -> clusters -> seed neurons        (Bio + CS1)
  bio/custom.py        user-supplied diseases: parse, check, save rows     (CS2)
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
  agent/agent.py       the agent loop (Gemma or Gemini, see below)         (CS2)
  agent/gemini.py      Gemini API client, rate-limit and overload fallback (CS2)
  agent/gemma.py       Gemma calls through generate_content                (CS2)
  agent/llm.py         one JSON call for either family                     (CS2)
  agent/summary.py     structured run summary card (JSON schema)           (CS2)
  agent/papers.py      paper PDF/text/DOI -> checked evidence rows for Bio (CS2)
  agent/prompts.py     system prompt rules                                 (Bio)
data/
  raw/                 downloads go here (not committed)
  processed/           output of prep (not committed; regenerate)
  evidence.json        hand-curated evidence table (committed)
  evidence_approved.json  rows approved from paper uploads (written by the app; not committed yet)
  evidence_proposals.json paper rows waiting for review (written by the app; gitignored)
  custom_diseases.json diseases added through the app, user-supplied (gitignored)
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

## Running

Setup and the run commands, for macOS and Windows, are in
[Set up on your machine](#set-up-on-your-machine). Notes on what the
commands do:

`--reload-exclude` keeps edits to `prep/` (the dataset build) from restarting
the API mid-request; every other file under `neurosim/`, `config.py` and
`models.py` included, still reloads it. The exclude needs `watchfiles`, which
is in requirements.txt (plain `uvicorn` ignores the flag without it).

The agent, the run summary and paper extraction use Gemma 4 by default
(`gemma-4-26b-a4b-it`, falling back to `gemma-4-31b-it` when it is busy or
rate-limited). Gemma is free on the Gemini API with the same `GEMINI_API_KEY`.
`NEUROSIM_LLM=gemini` switches all three back to Gemini Flash; restart the API
after changing it.

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
`papers.ask_model`, which sends the paper's text through `llm.json_reply`.
That is Gemma 4 by default and Gemini Flash with `NEUROSIM_LLM=gemini` (see
above); both use the same `GEMINI_API_KEY`.

## Your own disease

"Add your own" next to the Disease heading takes a disease table and runs
it through the same pipeline as Parkinson's. One row per gene:

| Column | Meaning |
| --- | --- |
| `disease` | Disease name, the same on every row |
| `human_gene` | Human gene symbol (HTT) |
| `fly_gene` | Fly ortholog. Only needed when the gene isn't in `data/evidence.json`'s ortholog table; the table's call wins otherwise |
| `affected` | Fly neurons lost or affected: dopamine clusters (`PPL1`, `PPL2`, `PPM1/2`, `PPM3`, `PAL`, `PAM`, `ALL_DA`) and/or FlyWire v783 cell types (`MBON01`, `KCg-m`), separated by `;` |
| `model_type` | `mutant`, `RNAi`, `overexpression` or `other` (optional) |
| `finding`, `citation`, `url` | What was found and where it comes from (optional) |
| `tier` | `high`, `medium` (default) or `low` |

Drop a CSV or JSON file in that shape (templates download from the panel:
`GET /custom/template.csv` and `.json`), or type the rows in. Every row is
checked like a paper row (`bio/custom.py`): the ortholog, each affected
name resolved to a cluster or a cell type with its neuron count and "did
you mean" suggestions, duplicates, and the confidence its seeds would get;
a cell type that isn't dopaminergic gets a note, because the engine's
random baseline draws dopamine neurons. Fix or drop the rows with problems,
then Save. Saved diseases go to `data/custom_diseases.json` (gitignored,
never into the curated table), appear in the picker tagged "your data" with
a remove button, and run like any other disease; the chain, the Overview
and the agent label their rows "user-supplied, not reviewed by Bio". A
cell type becomes a one-type cluster in the merged table, so nothing
downstream has a special case. Endpoints: `POST /custom/preview`,
`GET`/`POST /custom/diseases`, `DELETE /custom/diseases/{id}`,
`GET /custom/names?q=`.
