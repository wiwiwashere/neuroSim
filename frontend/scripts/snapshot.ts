// Saves the demo runs from a live API into public/demo/ for snapshot mode.
//
//   npm run snapshot                    # API at http://127.0.0.1:8000
//   NEUROSIM_API_URL=... npm run snapshot
//   npm run dev:snapshot                # app reads public/demo/ instead of the API
//
// Running it also warms the API's cache for every demo request.
// Node 22.6+ runs this TypeScript file directly (type stripping).

import { mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { snapshotPath } from "../src/lib/snapshot-keys.ts";

const API = process.env.NEUROSIM_API_URL ?? "http://127.0.0.1:8000";
const OUT = join(import.meta.dirname, "..", "public", "demo");

// The demo script: every gene knocked out, the agent's half-output follow-up,
// each seed cell type alone, and the PINK1 vs PRKN comparison.
const COMPARE_PAIRS: [string, string][] = [["PINK1", "PRKN"]];
const STRENGTHS = [0.5];
const LEVELS = ["super_region", "region", "cell_type"];

let saved = 0;

async function save(path: string, body?: object) {
  const init = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined;
  const res = await fetch(API + path, init);
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status} ${await res.text()}`);
  const data = await res.json();
  await writeFile(join(OUT, snapshotPath(path, init?.body)), JSON.stringify(data));
  saved++;
  return data;
}

async function saveRun(req: Record<string, unknown>) {
  const result = await save("/simulate", req);
  const id = encodeURIComponent(result.run_id);
  await save(`/runs/${id}`);
  await save(`/runs/${id}/sankey`);
  await save(`/runs/${id}/subgraph`);
  for (const n of result.top_neurons.slice(0, 10)) {
    await save(`/runs/${id}/neurons/${n.root_id}/explain`).catch(() => {});
  }
  return result;
}

await rm(OUT, { recursive: true, force: true });
await mkdir(OUT, { recursive: true });

const diseases: string[] = await save("/diseases");
const runIds = new Map<string, string>();

for (const disease of diseases) {
  const genes = await save(`/diseases/${encodeURIComponent(disease)}/genes`);
  for (const g of genes) {
    if (!g.simulatable) continue;
    const gene = g.human_gene as string;
    for (const hc of [false, true]) {
      const chain = await save(`/genes/${encodeURIComponent(gene)}/chain${hc ? "?high_confidence_only=true" : ""}`);
      const base = { human_gene: gene, high_confidence_only: hc };
      const ko = await saveRun({ ...base, mode: "knockout", strength: 1 });
      if (!hc) runIds.set(gene, ko.run_id);
      for (const strength of STRENGTHS) await saveRun({ ...base, mode: "reduce_output", strength });
      for (const t of chain.seed_types) await saveRun({ ...base, mode: "knockout", strength: 1, seed_cell_types: [t.cell_type] });
    }
  }
}

for (const [a, b] of COMPARE_PAIRS) {
  const ra = runIds.get(a);
  const rb = runIds.get(b);
  if (!ra || !rb) continue;
  for (const level of LEVELS) {
    await save(`/compare?run_a=${encodeURIComponent(ra)}&run_b=${encodeURIComponent(rb)}&level=${level}`).catch(() => {});
  }
}

console.log(`Saved ${saved} responses to public/demo/ from ${API}`);
