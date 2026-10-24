# Screens (CS2)

Next.js + Plotly/Recharts + Cytoscape.js, or Streamlit + Plotly +
st-cytoscape if nobody is a confident frontend developer. Either way, every
screen reads only from the API in `backend/neurosim/api/main.py`, and the
mocks make every endpoint work from hour 0.

| # | Screen | Endpoint | Shows | Notes |
| --- | --- | --- | --- | --- |
| 1 | Pick disease | `GET /diseases` | One card: Parkinson's | Generic list, never hard-coded |
| 2 | Pick gene | `GET /diseases/{d}/genes` | PINK1, PRKN, PARK7, LRRK2, SNCA with fly ortholog and evidence tier | SNCA shown greyed: "no fly ortholog" |
| 3 | Mapping chain | `GET /genes/{g}/chain` | Cards: human gene → fly gene (DIOPT) → clusters lost (citation) → connectome cell types (exact/inferred) → neuron count; confidence on each card | "High-confidence only" toggle re-calls with `high_confidence_only=true` |
| 4 | Choose perturbation | — | Knockout / reduce output, strength slider | Note under the slider: "results scale linearly with strength; rankings don't change" |
| 5 | Results, hero | `POST /simulate`, `GET /runs/{id}/sankey` | Sankey: seed clusters → super regions; disruption score with its z | The first thing a judge sees |
| 6 | Results, ranked | from `/simulate` result | Horizontal bars: vulnerability per region, chance range marked, above-chance in accent colour, plain-language function label | Toggle level: super region / region / cell type |
| 7 | Network drill-down | `GET /runs/{id}/subgraph`, `GET /runs/{id}/neurons/{rid}/explain` | Healthy and perturbed side by side, same positions; click a neuron for its top paths and its Codex link | ≤ 200 nodes, grouped by region |
| 8 | Compare genes | `GET /compare?run_a&run_b` | Two ranked lists side by side, shared regions highlighted, rank correlation | The demo's high point: PINK1 vs PRKN |
| 9 | Agent panel | `POST /agent/chat` | Chat, with each tool call shown as a chip ("ran simulation: PRKN, knockout") that links to its result | Always visible beside screens 5 to 8 |

Every results screen carries one line: "Structural dependency in the fly
connectome, not a prediction of symptoms." (Bio writes the final wording.)
