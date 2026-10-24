# Screens (CS2)

Next.js (App Router) + TypeScript, Tailwind CSS with shadcn/ui, TanStack
Query, Plotly (react-plotly.js) for the Sankey, ranked bars and comparison,
Cytoscape.js with a preset layout for the network. One charting library
everywhere. Every view reads only from the API in
`backend/neurosim/api/main.py`, and the mocks make every endpoint work from
hour 0.

Fallback, decided once at the hour-4 checkpoint: Streamlit + Plotly +
st-cytoscape against the same API.

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
| `npm run snapshot` | Save every demo request from the live API into `public/demo/` (also warms the API cache) |
| `npm run dev:snapshot` | App reading `public/demo/` instead of the API (`NEXT_PUBLIC_DEMO_SNAPSHOT=1`), so the demo survives a backend crash |
| `npm run typecheck`, `npm run lint`, `npm run build` | Checks |

## Layout

One workspace page instead of separate screens. A top bar shows the steps
(gene, chain, results, compare). The left column holds the disease and gene
pickers, the mapping chain and the perturbation controls. The centre has tabs
for Overview, Ranked, Network and Compare. The agent panel stays open on the
right.

| # | View | Where | Endpoint | Shows | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Pick disease | Left | `GET /diseases` | One card per disease | Generic list, never hard-coded |
| 2 | Pick gene | Left | `GET /diseases/{d}/genes` | Gene, fly ortholog (italic), evidence tier | SNCA greyed: "no fly ortholog"; clicking it explains why it can't be simulated |
| 3 | Mapping chain | Left | `GET /genes/{g}/chain` | Linked cards: human gene → fly gene (DIOPT) → clusters lost (finding, citation, tier) → connectome cell types (exact/inferred) → neuron count; confidence meter on each link | "High-confidence only" switch re-calls with `high_confidence_only=true` |
| 4 | Perturbation | Left | — | Knockout / reduce output, strength slider, Run | Note under the slider: "results scale linearly with strength; rankings don't change" |
| 5 | Overview (hero) | Centre tab | `POST /simulate`, `GET /runs/{id}/sankey` | Disruption score with its z and chance level, seed and reached counts; Sankey from seed clusters to super regions; top three regions | Seeds orange, above-chance regions blue, the rest grey |
| 6 | Ranked | Centre tab | from `/simulate` result | Horizontal bars of z vs random DA neurons, chance range (±1.96) shaded, above-chance bars in the accent colour, function label under each name; table view toggle | Level toggle: super region / region / cell type |
| 7 | Network | Centre tab | `GET /runs/{id}/subgraph`, `GET /runs/{id}/neurons/{rid}/explain` | Healthy and perturbed side by side at the backend's positions, grouped by region; lost drive drawn dashed; click a neuron for its top paths and its Codex link | ≤ 200 nodes |
| 8 | Compare | Centre tab | `GET /compare?run_a&run_b&level` | Rank correlation with a plain-words reading, summary sentence, shared/only chips, one paired dot chart (a row per region, a dot per gene, shared chance band) | The demo's high point: PINK1 vs PRKN |
| 9 | Agent panel | Right | `POST /agent/chat` | Chat with Gemini; each tool call is a chip ("ran simulation: PRKN, knockout") that opens its result. Runs in `run_ids` load into the centre views, so the screen changes when the agent runs something | The panel sends the run on screen as context, so "what if they lose half?" works. In snapshot mode a clearly labelled scripted stand-in calls the same API tools |
| 10 | Run summary | Overview tab | `POST /runs/{id}/summary` | Gemini's card: headline, top circuits with the run's own z-scores, caveats, one next experiment with a Run button | Asked for on click to save free-tier quota; hidden in snapshot mode |
| 11 | Evidence from a paper | Left | `POST /evidence/extract`, `POST /evidence/rows/{id}/decision` | Upload a PDF; Gemini proposes evidence rows with quote and page; Approve or Reject each | Approved rows go to `data/evidence_approved.json`, unverified until Bio checks the figures |

Every results view carries one line: "Structural dependency in the fly
connectome, not a prediction of symptoms." (Bio writes the final wording, in
`src/lib/format.ts`.) When the API serves mocks (`run_id` starts with
`mock-`) the top bar shows a "sample numbers" badge.

## Code map

| Path | What |
| --- | --- |
| `src/app/page.tsx` | The workspace layout |
| `src/lib/api.ts` | Every request; live vs snapshot switch |
| `src/lib/snapshot-keys.ts` | Request → `public/demo/` file name, shared with `scripts/snapshot.ts` |
| `src/lib/api-types.ts` | Generated from OpenAPI; don't edit |
| `src/lib/types.ts` | Friendly names for the generated types, plus the untyped endpoints |
| `src/lib/workspace.tsx` | Shared state: picks, runs, active tab. The agent writes here too |
| `src/lib/standin-agent.ts` | Scripted stand-in for `/agent/chat`, snapshot mode only |
| `src/components/charts/` | Plotly and Cytoscape wrappers |
| `src/components/workspace/` | The views above |

Colour: two data roles only, `--signal` (blue, above chance) and `--seed`
(orange, the perturbed neurons), on a warm neutral surface, defined in
`src/app/globals.css` for light and dark.
