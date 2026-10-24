// A scripted stand-in for POST /agent/chat, used only in snapshot mode, where
// there is no backend and so no Gemini. It is not an LLM: it recognises a few
// demo phrasings, calls the same API tools the real agent would (read from the
// snapshot), and writes its reply only from their results, so it can't invent
// numbers either. The panel labels its replies as the stand-in.

import { api } from "./api";
import type { AgentReply, SimulationRequest, SimulationResult, ToolCall } from "./types";

const GENES = ["PINK1", "PRKN", "PARK7", "LRRK2", "SNCA"];

export interface StandInReply extends AgentReply {
  results: SimulationResult[];
}

function parseStrength(text: string): number | null {
  if (/\bhalf\b/i.test(text)) return 0.5;
  const m = text.match(/(\d{1,3})\s*%/);
  return m ? Math.min(100, Number(m[1])) / 100 : null;
}

const fmtTop = (r: SimulationResult) => {
  const groups = Object.values(r.groups)[0] ?? [];
  const top = [...groups].sort((a, b) => b.z_score - a.z_score).slice(0, 3);
  return top.map((g) => `${g.group} (z ${g.z_score.toFixed(1)}${g.above_chance ? "" : ", within chance"})`).join(", ");
};

const summarise = (r: SimulationResult) =>
  `Disruption score ${(r.disruption_score * 100).toFixed(2)}% (z ${r.disruption_z.toFixed(1)} vs random DA neurons), ` +
  `${r.n_reached.toLocaleString()} neurons reached. Top regions: ${fmtTop(r)}.`;

export async function standInChat(text: string, context: SimulationRequest | null): Promise<StandInReply> {
  const mentioned = GENES.filter((g) => new RegExp(`\\b${g}\\b`, "i").test(text));
  const tool_calls: ToolCall[] = [];
  const results: SimulationResult[] = [];

  const simulate = async (req: SimulationRequest) => {
    tool_calls.push({ name: "run_simulation", arguments: { ...req } });
    const r = await api.simulate(req);
    results.push(r);
    return r;
  };

  const base: SimulationRequest = context ?? { human_gene: mentioned[0] ?? "PINK1" };

  // "Compare PINK1 and PRKN"
  if (/\bcompare\b|\bvs\.?\b|\bversus\b/i.test(text) && mentioned.length >= 2) {
    const [ga, gb] = mentioned;
    const ra = await simulate({ ...base, human_gene: ga, seed_cell_types: null });
    const rb = await simulate({ ...base, human_gene: gb, seed_cell_types: null });
    tool_calls.push({ name: "compare_runs", arguments: { run_a: ra.run_id, run_b: rb.run_id, level: "super_region" } });
    const cmp = await api.compare(ra.run_id, rb.run_id, "super_region");
    return {
      reply: `${cmp.summary} Shared top regions: ${cmp.shared_top.join(", ") || "none"}. Only ${ga}: ${cmp.only_a.join(", ") || "none"}. Only ${gb}: ${cmp.only_b.join(", ") || "none"}.`,
      tool_calls,
      run_ids: [ra.run_id, rb.run_id],
      interaction_id: null,
      results,
    };
  }

  // "What if they only lose half their output?"
  const strength = parseStrength(text);
  if (strength !== null) {
    const r = await simulate({ ...base, human_gene: mentioned[0] ?? base.human_gene, mode: "reduce_output", strength });
    return {
      reply: `Reduced the seeds’ output by ${Math.round(strength * 100)}%. ${summarise(r)}`,
      tool_calls,
      run_ids: [r.run_id],
      interaction_id: null,
      results,
    };
  }

  // "Test PPL101 alone"
  const cellType = text.match(/\b([A-Z]{2,4}\d{2,3}[a-z]?)\b/)?.[1];
  if (cellType && /\b(alone|only|just)\b/i.test(text)) {
    const r = await simulate({ ...base, seed_cell_types: [cellType] });
    return {
      reply: `Perturbed ${cellType} on its own. ${summarise(r)}`,
      tool_calls,
      run_ids: [r.run_id],
      interaction_id: null,
      results,
    };
  }

  // "Why these neurons?" / "Show the chain for PRKN"
  if (/\bwhy\b|\bchain\b|\bevidence\b/i.test(text)) {
    const gene = mentioned[0] ?? base.human_gene;
    tool_calls.push({ name: "get_gene_chain", arguments: { human_gene: gene } });
    const chain = await api.chain(gene, false);
    const ev = chain.seed_types.flatMap((t) => t.evidence)[0];
    return {
      reply:
        `${gene} maps to fly ${chain.ortholog.fly_genes.join(", ")} (DIOPT ${chain.ortholog.diopt_score ?? "n/a"}). ` +
        (ev ? `${ev.finding} (${ev.citation}, ${ev.tier} tier). ` : "") +
        `That gives ${chain.seed_types.map((t) => `${t.cell_type} (${t.n_neurons}, ${t.match})`).join(", ")} as seeds.`,
      tool_calls,
      run_ids: [],
      interaction_id: null,
      results,
    };
  }

  // "Knock out PRKN" / "Run PINK1"
  if (mentioned.length >= 1 || /\b(run|knock ?out|simulate)\b/i.test(text)) {
    const r = await simulate({ ...base, human_gene: mentioned[0] ?? base.human_gene, mode: "knockout", strength: 1, seed_cell_types: null });
    return { reply: `Knocked out ${r.request.human_gene}’s seed neurons. ${summarise(r)}`, tool_calls, run_ids: [r.run_id], interaction_id: null, results };
  }

  return {
    reply:
      "I’m the scripted stand-in, so I only understand a few requests: “knock out PRKN”, “what if they only lose half their output?”, “test PPL101 alone”, “compare PINK1 and PRKN”, or “why these neurons?”.",
    tool_calls,
    run_ids: [],
    interaction_id: null,
    results,
  };
}
