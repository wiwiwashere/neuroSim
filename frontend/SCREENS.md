# Screens (CS2)

What the built app looks like and which endpoint feeds each part. Next.js 15
(App Router) + React 19 + TypeScript, Tailwind CSS 4 with shadcn/ui, TanStack
Query, Plotly (react-plotly.js) for the Sankey, ranked bars and comparison,
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
| 1 | Disease | Left | `GET /diseases` | One card per disease, display name from `format.ts` | Generic list, never hard-coded. Picking one clears the gene |
| 2 | Gene | Left | `GET /diseases/{d}/genes` | Gene (mono), fly ortholog(s) in italics, evidence tier badge | A gene with no fly ortholog (SNCA) stays listed in grey with "can't simulate"; picking it shows why in the chain slot |
| 3 | Why these neurons? (mapping chain) | Left | `GET /genes/{g}/chain` | Linked cards on a rail: human gene → fly ortholog with DIOPT score, relationship and confidence meter → dopamine clusters lost, each finding with its citation link, model type and tier → connectome cell types with an exact/inferred tag and confidence meter → total seed neurons | "High-confidence only" switch re-fetches with `high_confidence_only=true` and is sent with the run |
| 4 | Perturbation | Left, pinned to the bottom of the column | — | Knockout / Reduce output toggle and a Run button ("Run again" for a request already run). The "Output lost" slider (5–100%) appears only for Reduce output, with the note "results scale linearly with strength; rankings don't change" | Knockout always sends strength 1. The empty results area offers the same Run button |
| 5 | Overview (hero) | Centre tab | `POST /simulate`, `GET /runs/{id}/sankey` | Headline: disruption as a multiple of chance ("3.2× chance"), its z and a plain reading ("far above chance"). Two equal tiles: seed disruption % vs random DA neurons of the same count. Seed and reached counts within N hops. Sankey "Where does the damage go?" from seed clusters to super regions. "Most dependent regions": top three by z with function label | Seeds orange, above-chance regions blue, the rest grey |
| 6 | Ranked | Centre tab | from the `/simulate` result | "Which effects are real, and which are chance?" Horizontal bars of z vs random DA neurons, ±1.96 band shaded, bars that pass FDR (q < 0.05) blue, function label under each name. "Show table" adds group, function, neurons, strong hits, direct %, z, q | Level toggle: super region / region / cell type; a level the run didn't return is disabled |
| 7 | Network | Centre tab | `GET /runs/{id}/subgraph`, `GET /runs/{id}/neurons/{rid}/explain` | Healthy and "With PRKN knockout" side by side at the same positions; lost drive dashed, seeds orange. The most-hit neuron starts selected; clicking one opens its impact, strongest paths from the seeds, and a "View in Codex (3D)" link | Positions come from the backend's x/y; without them, one column per region. At most `SUBGRAPH_MAX_NODES` (200) |
| 8 | Compare | Centre tab | `POST /simulate`, `GET /compare?run_a&run_b&level` | The active run against a second one: pick an earlier run, or pick a gene and "Run and compare" (same mode and strength). Spearman ρ tile with a plain reading and the level, the summary sentence, chips for in both top lists / only A / only B, and a paired dot chart "Do they hit the same circuits?" (a row per region, a dot per gene, shared chance band) | The demo's high point: PINK1 vs PRKN. Falls back to super region if either run lacks the chosen level |
| 9 | Ask neuroSim (agent) | Right | `POST /agent/chat`, `GET /runs/{id}` | Four suggested questions, then a chat. Each tool call is a chip ("ran simulation: PRKN, knockout", "compared the two runs", "read mapping chain: PINK1", "explained neuron …") that opens its result. Runs the agent makes load into the centre views (a comparison opens the Compare tab), so the screen changes when the agent runs something | If `/agent/chat` returns 5xx, or in snapshot mode, a scripted stand-in calls the same API tools; its replies are labelled "scripted stand-in" |

Above the results, a "Showing" menu lists every run made this session, the
agent's marked "(agent)", and switches the centre views between them. Before
the first run the centre shows "Ready to perturb PRKN" with a Run button.

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
| `src/lib/workspace.tsx` | Shared state: picks, runs, active and compared run, tab. The agent writes here too |
| `src/lib/standin-agent.ts` | Scripted stand-in for `/agent/chat` |
| `src/lib/format.ts` | Number formats, plain readings of z and ρ, the scope line |
| `src/lib/theme.tsx` | Light/dark, and the colour tokens resolved to hex for Plotly and Cytoscape |
| `src/components/charts/` | `sankey`, `ranked-bars`, `paired-dots` (Plotly), `network` (Cytoscape), `plot` (shared Plotly setup) |
| `src/components/workspace/` | `top-bar`, `gene-picker`, `mapping-chain`, `perturbation`, `results` (Overview, Ranked, Network, run switcher), `compare`, `agent-panel` |
| `next.config.ts` | Proxies `/api/*` to FastAPI, so the backend needs no CORS |
| `scripts/snapshot.ts` | Writes `public/demo/` for snapshot mode |

Colour: two data roles only, `--signal` (blue, above chance) and `--seed`
(orange, the perturbed neurons), plus `--faint` / `--chance` greys, on a warm
neutral surface, defined in `src/app/globals.css` for light and dark.
