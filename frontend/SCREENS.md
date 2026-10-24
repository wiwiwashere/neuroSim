# Screens (CS2)

What the built app looks like and which endpoint feeds each part. Next.js 15
(App Router) + React 19 + TypeScript, Tailwind CSS 4 with shadcn/ui, TanStack
Query, Plotly (react-plotly.js) for the ranked bars and comparison,
Cytoscape.js with preset positions for the network. Every view reads only from
the API in `backend/neurosim/api/main.py`; while `NEUROSIM_MOCKS=1` (the
default) the API serves fixed sample payloads, so every view works before the
engine does.

## Running it

```
# API on :8000 (mocks on by default)
cd backend && uvicorn neurosim.api.main:app --reload
# App on :3000; /api/* is proxied to NEUROSIM_API_URL (default http://127.0.0.1:8000)
cd frontend && npm install && npm run dev
```

| Command | What it does |
| --- | --- |
| `npm run dev` | App against the live API |
| `npm run gen:api` | Regenerate `src/lib/api-types.ts` from FastAPI's OpenAPI schema (API must be running). Do this whenever `models.py` changes |
| `npm run snapshot` | Save every demo request from the live API into `public/demo/` (also warms the API cache). Needs Node 22.6+ |
| `npm run dev:snapshot` | App reading `public/demo/` instead of the API (`NEXT_PUBLIC_DEMO_SNAPSHOT=1`), so the demo survives a backend crash |
| `npm run typecheck`, `npm run lint`, `npm run build` | Checks |

The snapshot covers every simulatable gene knocked out, at 50% output and
with each seed cell type alone, with and without "high-confidence only", plus
PINK1 vs PRKN at all three levels.

## Layout

One workspace page (`src/app/page.tsx`), not separate screens. Three columns
on wide screens: inputs on the left, results in the centre, the agent on the
right. Below 1280 px the agent panel moves under the other two; on phones
everything stacks.

**Top bar.** Logo, then the steps Gene / Chain / Results / Compare, numbered,
filled in as they are done and clickable (scrolls to the step or switches tab).
On the right: a dashed "sample numbers" badge when the run came from the mocks
(`run_id` starts with `mock-`), a "snapshot mode" badge, and the light/dark
toggle (follows the OS until the person picks, then remembered in
localStorage).

| # | View | Where | Endpoint | Shows | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Pick disease | Left | `GET /diseases` | One card per disease | Generic list, never hard-coded |
| 2 | Pick gene | Left | `GET /diseases/{d}/genes` | Gene, fly ortholog (italic), evidence tier | SNCA greyed: "no fly ortholog"; genes with an ortholog but no evidence row (VPS35, GBA1, ...) say "no evidence yet"; clicking either explains why it can't be simulated, and the second also shows its atlas expression |
| 3 | Mapping chain | Left | `GET /genes/{g}/chain` | Linked cards: human gene → fly gene (DIOPT) → clusters lost (finding, citation, tier) → connectome cell types (exact/inferred) → neuron count; confidence meter on each link; rows from uploaded papers carry an "uploaded paper" tag and their quote; an "Expression in fly neurons · atlas" card gives the fly genes' TPM across PAM types (values per type behind a toggle) and says which seed clusters the atlas never profiled, and PAM seed types show their TPM | "High-confidence only" switch re-calls with `high_confidence_only=true` |
| 4 | Perturbation | Left | — | Knockout / reduce output, strength slider, Run | Note under the slider: "results scale linearly with strength; rankings don't change" |
| 5 | Overview (hero) | Centre tab | `POST /simulate`, `GET /runs/{id}/sankey` | One-sentence takeaway ("PINK1 knockout in 4 PPL1 dopamine neurons removes 2.0× the downstream input that 4 random ones do"), seeds vs random drawn as two bars on one scale, then one bar per super region for its share of the damage (summed from the Sankey links), split by seed cluster when there are several; below it, "The evidence behind these seeds": each evidence row with citation and tier, uploaded-paper rows tagged with their quote, then the same expression note as the chain | Above-chance regions blue, the rest grey |
| 6 | Ranked | Centre tab | from `/simulate` result | Horizontal bars of z vs random DA neurons, chance range (±1.96) shaded, above-chance bars in the accent colour, function label under each name; table view toggle | Level toggle: super region / region / cell type |
| 7 | Network | Centre tab | `GET /runs/{id}/subgraph`, `GET /runs/{id}/neurons/{rid}/explain` | Flow by synapse (default): seeds, then one column per synapse away (hops found client-side from the drawn edges), rows merged by cell type or one per neuron, grey width = connection, orange width = drive lost, blue = above chance in Ranked; hover traces a row's path. Toggle back to healthy and perturbed side by side at the backend's positions. Click a row or neuron for its top paths and its Codex link | ≤ 200 nodes |
| 8 | Compare | Centre tab | `GET /compare?run_a&run_b&level` | Rank correlation with a plain-words reading, summary sentence, shared/only chips, one paired dot chart (a row per region, a dot per gene, shared chance band) | The demo's high point: PINK1 vs PRKN |
| 9 | Agent panel | Right | `POST /agent/chat` | Chat with Gemini; each tool call is a chip ("ran simulation: PRKN, knockout") that opens its result. Runs in `run_ids` load into the centre views, so the screen changes when the agent runs something | The panel sends the run on screen as context, so "what if they lose half?" works. In snapshot mode a clearly labelled scripted stand-in calls the same API tools |
| 10 | Run summary | Overview tab | `POST /runs/{id}/summary` | Gemini's card: headline, top circuits with the run's own z-scores, caveats, one next experiment with a Run button | Asked for on click to save free-tier quota; hidden in snapshot mode |
| 11 | Evidence from a paper | Left | `POST /evidence/extract`, `GET /evidence/proposals`, `POST /evidence/rows/{id}/decision`, `GET`/`DELETE /evidence/approved` | Drop a PDF, paste text, or give a DOI/PMID; the model proposes rows with a quote (checked word for word, page from the PDF), mapped clusters (struck through if unknown, red if the quote doesn't name them), the seeds' confidence and any problems; Edit, Approve or Reject each; approved rows listed with a remove button | Says what was read (PDF, text, full text or abstract) and warns when only the abstract was available or the backup model read it. Pending rows survive reloads. Approved rows go to `data/evidence_approved.json`, unverified until Bio checks the figures, and seed the next run: the chain and the Overview's "evidence behind these seeds" mark them "uploaded paper" |

Every results view ends with one line: "Structural dependency in the fly
connectome, not a prediction of symptoms." (Bio writes the final wording, in
`src/lib/format.ts`.)

## Code map

| Path | What |
| --- | --- |
| `src/app/page.tsx` | The workspace layout |
| `src/app/providers.tsx` | TanStack Query, theme and workspace providers |
| `src/lib/api.ts` | Every request; live vs snapshot switch; Codex link |
| `src/lib/snapshot-keys.ts` | Request → `public/demo/` file name, shared with `scripts/snapshot.ts` |
| `src/lib/api-types.ts` | Generated from OpenAPI; don't edit |
| `src/lib/types.ts` | Friendly names for the generated types, plus the untyped endpoints |
| `src/lib/workspace.tsx` | Shared state: picks, runs, active tab. The agent writes here too |
| `src/lib/standin-agent.ts` | Scripted stand-in for `/agent/chat`, snapshot mode only |
| `src/components/charts/` | Plotly and Cytoscape wrappers |
| `src/components/workspace/` | The views above |

Colour: two data roles only, `--signal` (blue, above chance) and `--seed`
(orange, the perturbed neurons), plus `--faint` / `--chance` greys, on a warm
neutral surface, defined in `src/app/globals.css` for light and dark.
