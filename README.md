# neuroSim — Disease Circuit Simulator

Give it a Parkinson's gene. It finds the fly neurons that published studies show
die when that gene is broken, traces where those neurons send their output in
the FlyWire connectome, and ranks which brain regions and cell types lose an
unusually large share of their input compared with chance.

Parkinson's is built in (PINK1, PRKN, PARK7 and more). Any other disease can
be added from the app as a small table of genes and affected neurons (see
[Your own disease](#your-own-disease)). An AI agent built on **Gemma 4**
answers questions about a run, runs follow-up experiments itself, and turns
papers into evidence rows.

Results are hypotheses about fly circuits: structural dependency in one
connectome, not a prediction of symptoms.

## What it does

- **Gene to neurons.** Human gene → fly ortholog (DIOPT) → the dopamine
  clusters lost in fly models of that gene → FlyWire cell types → individual
  neurons, with a citation and a confidence at every link.
- **The simulation.** The seed neurons lose their output; the engine
  measures, for every other neuron in the brain, how much of its input
  disappears, directly and within 3 synapses (input-normalised weights,
  linear propagation with decay 0.5). Scores are averaged per region, super
  region, cell type and super class.
- **Against chance.** Every result is compared with 200 runs that remove the
  same number of random dopamine neurons, giving a z-score, an empirical
  p-value and a Benjamini–Hochberg q-value per group. Only groups with
  q < 0.05 and z > 0 are called "above chance".
- **Views.** A mapping chain with the evidence, the direct targets of the
  lost neurons, an Overview with a one-sentence takeaway, ranked bars, a
  network view (flow by synapse, healthy vs perturbed, and a 3D connectome
  that plays degeneration over time), and a gene-vs-gene comparison
  (PINK1 vs PRKN).
- **The agent.** Chat that calls the same API tools the screens use, a
  one-click run summary, and paper upload that proposes evidence rows for a
  person to approve.

How every number is computed, and why: [docs/ENGINE_DESIGN.md](docs/ENGINE_DESIGN.md).
What each screen shows and which endpoint feeds it: [frontend/SCREENS.md](frontend/SCREENS.md).

## Team

Built in 48 hours by a team of three.

| Who | Role | Folder | What |
| --- | --- | --- | --- |
| Kait | Biology | `data/evidence.json`, `data/*.csv`, `backend/neurosim/bio/`, `backend/neurosim/agent/prompts.py` | Gene → fly gene → dying DA clusters → connectome cell types, with citations and confidence; the expression and one-hop target tables; agent rules and disclaimers |
| Mohana | Simulation engine | `backend/neurosim/prep/`, `backend/neurosim/engine/`, `tests/` | Data prep, graph, perturbation, propagation, vulnerability scoring, random baseline, the 3D view and its degeneration dynamics. **Read `docs/ENGINE_DESIGN.md` first.** |
| Winnie | App and agent | `backend/neurosim/api/`, `backend/neurosim/agent/`, `frontend/` | FastAPI, caching, the Gemma agent, paper upload, custom diseases, all screens |

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

Open `.env` and paste a Gemini API key after `GEMINI_API_KEY=`. A free key
from https://aistudio.google.com/apikey is enough (team members can ask
Winnie for the team's free-tier key in a direct message). The same key
serves Gemma and Gemini. `.env` is gitignored: never commit it, paste it in a
chat, or put it in code. The key is only needed for the agent chat, the run
summary and paper upload; everything else works without it. Restart the API
after editing `.env`.

### 3. Data (needed for real results)

The engine runs on the FlyWire connectome, which you download once and turn
into `data/processed/`. Without it the app still starts, but the API serves
fixed sample numbers and the top bar shows a "sample numbers" badge, so you
can try every screen on a fresh clone.

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
types; it doesn't read the two region files. It keeps neuron pairs with 5 or
more synapses (summed over neuropils), which gives about 139k neurons and
2.7 million connections, 610 of them dopamine neurons by their annotated
transmitter. More detail on each file is in [Data files](#data-files).

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

Use npm (the repo's `package-lock.json`), not pnpm. If you installed before
the 3D view landed, run `npm install` again: it added `three` and the
`@react-three/*` packages.

Open http://localhost:3000. The API's own docs are at
http://127.0.0.1:8000/docs. Run the tests from the repo root with
`python -m pytest tests/`.

The API loads the connectome into memory on the first run and keeps it.
Every run is cached by its request and settings, so asking for the same run
again returns at once.

### Working on the engine

- **Where the math is.** `input_normalize` in `backend/neurosim/engine/graph.py`,
  then `perturb.py`, `propagate.py`, `vulnerability.py` and `baseline.py`, in
  the order of `docs/ENGINE_DESIGN.md`. Every tunable constant (synapse
  threshold, hops, decay, number of draws, group size, FDR level) is in
  `backend/neurosim/config.py`. `pipeline.py` is the one entry point the API
  and the agent call.
- **The tests.** `tests/test_engine_toy.py` checks every function against a
  6-neuron graph with hand-computed answers (ENGINE_DESIGN.md, section 5);
  `tests/test_engine_core.py` and `tests/test_pipeline.py` cover the rest.
- **Try it without the data.** `python -m neurosim.engine.validation --synthetic`
  (from `backend/`) runs the PAM → mushroom body check on a small made-up
  brain. Starting the API with `NEUROSIM_SYNTHETIC=1` runs the whole app on
  that brain. Its numbers mean nothing biologically.
- **Validate on the real data.** `python -m neurosim.engine.validation`
  (without `--synthetic`) seeds the PAM neurons from Riemensperger et al.
  2013 and checks that the β′-lobe mushroom body output neurons come out
  above chance (ENGINE_DESIGN.md, section 9).
- **Force sample numbers.** `NEUROSIM_MOCKS=1` makes the API serve the fixed
  payloads in `api/mocks.py` even when the data is there, which is handy for
  frontend work:
  - macOS: `NEUROSIM_MOCKS=1 python -m uvicorn neurosim.api.main:app --reload --reload-dir neurosim --reload-exclude "neurosim/prep/*"`
  - Windows (PowerShell): `$env:NEUROSIM_MOCKS="1"` first, then the usual uvicorn line in the same terminal.

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
  `data/raw/` (step 3). Until then the app runs on sample numbers.
- **The top bar says "sample numbers"**: the API didn't find
  `data/processed/` when it started (or `NEUROSIM_MOCKS=1` is set). Build the
  dataset (step 3) and restart the API.
- **The chat panel says "Can't reach the neuroSim API on :8000"**: the API
  isn't running or crashed; look at its terminal.
- **The agent says the key was rejected**: `.env` is missing or the key is
  empty or wrong. Fix it and restart the API.

## Layout

```
backend/neurosim/
  config.py            all tunable constants in one place (thresholds, decay, hops, ...)
  models.py            data contracts shared by engine, API, agent and frontend
  prep/build_dataset.py    offline: raw FlyWire files -> data/processed/*
  prep/download_labels.py  fetch FlyWire cell type / region / NT labels into data/raw/
  bio/evidence.py      gene -> ortholog -> clusters -> seed neurons
  bio/expression.py    expression atlas values attached to the seeds (context only)
  bio/targets.py       direct one-synapse targets of a gene's lost clusters
  bio/custom.py        user-supplied diseases: parse, check, save rows
  engine/
    graph.py           load connectome, input-normalized weight matrix
    perturb.py         perturbation modes -> initial deficit vector
    propagate.py       multi-hop impact
    vulnerability.py   per-neuron -> per-group scores, disruption score
    baseline.py        random-seed null distribution, z-scores, p- and q-values
    subgraph.py        small graph for drawing, Sankey links, top paths
    compare.py         gene vs gene, leave-one-cluster-out
    degeneration.py    Wilson–Cowan time-series for the 3D view (neurolib)
    validation.py      PAM -> mushroom body check (real or synthetic brain)
    synthetic.py       small made-up brain for tests and NEUROSIM_SYNTHETIC=1
    pipeline.py        one call that runs a whole experiment
  api/main.py          FastAPI endpoints
  api/mocks.py         fixed sample payloads, used when there is no connectome data
  agent/tools.py       tools the LLM may call (thin wrappers on pipeline)
  agent/agent.py       the agent loop (Gemma or Gemini, see below)
  agent/gemini.py      Gemini API client, rate-limit and overload fallback
  agent/gemma.py       Gemma calls through generate_content
  agent/llm.py         one JSON call for either family
  agent/summary.py     structured run summary card (JSON schema)
  agent/papers.py      paper PDF/text/DOI -> checked evidence rows
  agent/prompts.py     system prompt rules
data/
  raw/                 downloads go here (not committed)
  processed/           output of prep (not committed; regenerate)
  evidence.json        hand-curated evidence table
  evidence_approved.json  rows approved from paper uploads (written by the app)
  evidence_proposals.json paper rows waiting for review (written by the app; gitignored)
  custom_diseases.json diseases added through the app, user-supplied (gitignored)
  expression_table.csv Davis et al. 2020 cell-type expression atlas (PAM types)
  downstream_by_flywire_type.csv  one-hop targets of each DA cluster, FlyWire v783
  combinedDatabase.csv, clusterFBbt.csv, seed_group_summary.csv  Kait's source tables
docs/ENGINE_DESIGN.md  how the simulation and vulnerability model work, and why
frontend/              Next.js workspace app; SCREENS.md maps each view to its endpoint
tests/                 engine, pipeline, API, agent, evidence and custom-disease tests
```

## Data files

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

   If the annotations are already in place and only the Zenodo region files
   are missing, fetch just those (from the repo root, venv active):

   ```
   cd backend
   python -m neurosim.prep.download_labels --only neuropil_pre neuropil_post
   ```

   It prints `verified md5` for each file and adds them to the manifest.

   Codex serves similar tables but needs a personal API token, so prep doesn't
   use it. All FlyWire data is CC BY 4.0: cite Dorkenwald et al. 2024 and
   Schlegel et al. 2024 (Nature), Eckstein et al. 2024 (Cell) for the
   neurotransmitter predictions, and Berg et al. 2026 (Cell) for the v3
   annotations.

The dopamine pool is defined by the annotated transmitter (`known_nt`) first
and the predicted one (`top_nt`) only where no annotation exists, because
`top_nt` labels thousands of Kenyon cells as dopaminergic.

## Running

Setup and the run commands, for macOS and Windows, are in
[Set up on your machine](#set-up-on-your-machine). Notes on what the
commands do:

`--reload-exclude` keeps edits to `prep/` (the dataset build) from restarting
the API mid-request; every other file under `neurosim/`, `config.py` and
`models.py` included, still reloads it. The exclude needs `watchfiles`, which
is in requirements.txt (plain `uvicorn` ignores the flag without it).

The API picks its data source at startup: the real engine when
`data/processed/` exists, otherwise the sample payloads in `api/mocks.py`
(run IDs start with `mock-`, and the app and the agent both say the numbers
are samples). `NEUROSIM_MOCKS=1` or `=0` forces either.
`NEUROSIM_SYNTHETIC=1` runs the real engine on a small made-up brain
(`engine/synthetic.py`), so the full pipeline can be tried before prep has
run. Its numbers mean nothing biologically.

## Built with Gemma

The agent chat, the run summary and paper extraction all run on **Gemma 4**
through the Gemini API's free tier: `gemma-4-26b-a4b-it` by default, falling
back to `gemma-4-31b-it` when it is busy or rate-limited. Gemma uses the
same `GEMINI_API_KEY`, and the whole app runs at no cost.

- **Chat with tools.** Gemma calls the same functions the screens use
  (`agent/tools.py`): list diseases, show a gene's chain and direct targets,
  run a simulation, compare two runs, explain why a neuron is hit. Runs it
  starts load into the centre views, so the screen changes as it works.
- **Run summary.** One click turns a run into a card with a headline, the
  top circuits with their own z-scores, caveats and one next experiment
  with a Run button. The z-scores on the card are the run's own.
- **Paper upload.** Gemma reads a paper and proposes evidence rows with a
  verbatim quote, which the app checks before a person approves them
  ([Evidence from papers](#evidence-from-papers)).

Guardrails for the free tier are in `config.py`: library retries off, a
2-minute cap per chat turn, a 4-minute cap on paper extraction, and a
fallback model on timeout. `NEUROSIM_LLM=gemini` switches all three
features to Gemini Flash; restart the API after changing it.

## The 3D view

Network → "3D Connectome" draws the run's subgraph (up to 200 neurons, the
seeds plus the most affected ones) in three dimensions with Three.js
(`frontend/src/components/charts/network-3d.tsx`), one layer per region.
Seeds turn orange, neurons in above-chance groups are marked blue, and every
other neuron shades from pale to dark red as it loses input, hop by hop. Play
or scrub the timeline to watch the seeds lose function: the colours follow
a Wilson–Cowan neural-mass simulation of the most affected regions
(`engine/degeneration.py`, neurolib's `WCModel`, served by
`GET /runs/{id}/dynamics`), where the seed regions' drive fades linearly
over the simulated time. This is a visual narrative of progressive loss, not
part of the scoring: the ranked results come only from the propagation and
the random baseline. Clicking a neuron opens its top paths and a link to its
real 3D shape on FlyWire Codex.

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
[Built with Gemma](#built-with-gemma)); both use the same `GEMINI_API_KEY`.

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

Drop a CSV or JSON file in that shape, or type the rows in. "Use the
example" fills the form with two ready-made rows (Huntington's disease,
HTT → htt, affecting `PAM; PPL1` and `MBON01; MBON03`, real FlyWire names
that pass every check) and checks them, so Save and Run are one click
each; the same rows download as the CSV/JSON template
(`GET /custom/template.csv` and `.json`). They illustrate the format and
are not a reviewed finding.

Every row is checked like a paper row (`bio/custom.py`): the ortholog, each
affected name resolved to a cluster or a cell type with its neuron count and
"did you mean" suggestions, duplicates, and the confidence its seeds would
get; a cell type that isn't dopaminergic gets a note, because the engine's
random baseline draws dopamine neurons. A gene whose rows name more neurons
than that pool has (610 on FlyWire v783; `KCg-m` alone is about 2,200) is
refused, because the baseline samples without replacement and would have no
chance level to offer; `pipeline.run_simulation` turns the same case into a
422 for rows saved before the check. Fix or drop the rows with problems,
then Save. Saved diseases go to `data/custom_diseases.json` (gitignored,
never into the curated table), appear in the picker tagged "your data" with
a remove button, and run like any other disease; the chain, the Overview
and the agent label their rows "user-supplied, not reviewed by Bio". A
cell type becomes a one-type cluster in the merged table, so nothing
downstream has a special case. Endpoints: `POST /custom/preview`,
`GET`/`POST /custom/diseases`, `DELETE /custom/diseases/{id}`,
`GET /custom/names?q=`.

## Limitations

The model is linear, unsigned and static; dopamine also acts by volume
transmission, which synapse counts miss; seeds are only as good as the
papers behind them; and FAFB is a single female fly. The full list, and what
each choice means for the results, is in
[docs/ENGINE_DESIGN.md, section 10](docs/ENGINE_DESIGN.md#10-known-limitations).
