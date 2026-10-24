// Lays the drawn subgraph out as a left-to-right flow: seeds in the first
// column, then one column per synapse away from them. Neurons can be merged
// by cell type so a 200-neuron subgraph reads as a few dozen rows.
//
// Works on the Subgraph contract alone (models.py): hops are not sent by the
// backend, so they are the shortest path from any seed over the drawn edges.

import type { GraphEdge, GraphNode, Subgraph } from "./types";

export type FlowGrouping = "cell_type" | "neuron";

export interface FlowRow {
  key: string;
  column: number;
  label: string;
  /** The region most of the row's neurons sit in. */
  region: string;
  /** Most hit first. */
  nodes: GraphNode[];
  /** Mean impact of the row's neurons (for seeds, the perturbation strength). */
  impact: number;
  isSeed: boolean;
  /** The overflow row that stands in for the lowest-impact rows of a column. */
  isMore: boolean;
}

export interface FlowColumn {
  title: string;
  rows: FlowRow[];
}

export interface FlowLink {
  source: string;
  target: string;
  /** Summed input fraction of the edges this link stands for. */
  weight: number;
  /** Summed drive removed by the perturbation. */
  lost: number;
  synapses: number;
  edges: number;
}

export interface Flow {
  columns: FlowColumn[];
  links: FlowLink[];
  /** Edges that don't step one column right (feedback or lateral); not drawn. */
  hiddenEdges: number;
}

/** Hops at or past this share the last column. */
const MAX_HOP = 3;
const UNREACHED = -1;

/** Shortest hop count from any seed, over the directed edges in the view. */
export function hopsFromSeeds(graph: Subgraph): Map<string, number> {
  const out = new Map<string, string[]>();
  for (const e of graph.edges) out.set(e.source, [...(out.get(e.source) ?? []), e.target]);
  const hop = new Map<string, number>();
  let frontier = graph.nodes.filter((n) => n.is_seed).map((n) => n.id);
  for (const id of frontier) hop.set(id, 0);
  for (let h = 1; frontier.length > 0; h++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const t of out.get(id) ?? []) {
        if (!hop.has(t)) {
          hop.set(t, h);
          next.push(t);
        }
      }
    }
    frontier = next;
  }
  for (const n of graph.nodes) if (!hop.has(n.id)) hop.set(n.id, UNREACHED);
  return hop;
}

function columnTitle(hop: number) {
  if (hop === 0) return "Seeds";
  if (hop === UNREACHED) return "Further, path not drawn";
  if (hop >= MAX_HOP) return `${MAX_HOP}+ synapses away`;
  return hop === 1 ? "1 synapse away" : `${hop} synapses away`;
}

const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / Math.max(xs.length, 1);

function mostCommon(xs: string[]) {
  const count = new Map<string, number>();
  for (const x of xs) count.set(x, (count.get(x) ?? 0) + 1);
  return [...count.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "";
}

function makeRow(key: string, column: number, label: string, nodes: GraphNode[], isMore = false): FlowRow {
  const sorted = [...nodes].sort((a, b) => b.impact - a.impact);
  return {
    key,
    column,
    label,
    region: mostCommon(nodes.map((n) => n.group)),
    nodes: sorted,
    impact: mean(nodes.map((n) => n.impact)),
    isSeed: nodes.every((n) => n.is_seed),
    isMore,
  };
}

export function buildFlow(graph: Subgraph, grouping: FlowGrouping, maxRows = 12): Flow {
  const hop = hopsFromSeeds(graph);
  const hopOf = (n: GraphNode) => {
    const h = hop.get(n.id) ?? UNREACHED;
    return h === UNREACHED ? h : Math.min(h, MAX_HOP);
  };

  // Columns left to right: seeds, 1, 2, 3+, then anything the drawn edges don't reach.
  const hops = [...new Set(graph.nodes.map(hopOf))].sort((a, b) => (a === UNREACHED ? 1 : b === UNREACHED ? -1 : a - b));

  const rowOfNode = new Map<string, string>();
  const columns: FlowColumn[] = hops.map((h, column) => {
    const members = graph.nodes.filter((n) => hopOf(n) === h);
    const buckets = new Map<string, GraphNode[]>();
    for (const n of members) {
      const k = grouping === "neuron" ? n.id : n.label;
      buckets.set(k, [...(buckets.get(k) ?? []), n]);
    }
    let rows = [...buckets.entries()].map(([k, nodes]) =>
      makeRow(`${column}|${k}`, column, grouping === "neuron" ? nodes[0].label : k, nodes),
    );
    rows.sort((a, b) => (h === 0 ? a.label.localeCompare(b.label) : b.impact - a.impact));
    if (rows.length > maxRows) {
      const rest = rows.slice(maxRows - 1);
      const unit = grouping === "neuron" ? "neurons" : "types";
      rows = [
        ...rows.slice(0, maxRows - 1),
        makeRow(`${column}|more`, column, `+${rest.length} more ${unit}`, rest.flatMap((r) => r.nodes), true),
      ];
    }
    for (const r of rows) for (const n of r.nodes) rowOfNode.set(n.id, r.key);
    return { title: columnTitle(h), rows };
  });

  const columnOfRow = new Map(columns.flatMap((c, i) => c.rows.map((r) => [r.key, i] as const)));
  const links = new Map<string, FlowLink>();
  let hiddenEdges = 0;
  for (const e of graph.edges as GraphEdge[]) {
    const s = rowOfNode.get(e.source);
    const t = rowOfNode.get(e.target);
    if (!s || !t) continue;
    if (columnOfRow.get(t)! !== columnOfRow.get(s)! + 1 || hops[columnOfRow.get(s)!] === UNREACHED) {
      hiddenEdges++;
      continue;
    }
    const k = `${s}->${t}`;
    const link = links.get(k) ?? { source: s, target: t, weight: 0, lost: 0, synapses: 0, edges: 0 };
    link.weight += e.weight;
    link.lost += e.lost;
    link.synapses += e.synapses;
    link.edges += 1;
    links.set(k, link);
  }
  return { columns, links: [...links.values()], hiddenEdges };
}

/** Rows linked to `key` through the drawn links, upstream and downstream. */
export function connectedRows(flow: Flow, key: string): Set<string> {
  const keep = new Set([key]);
  const walk = (from: "source" | "target", to: "source" | "target") => {
    let frontier = [key];
    while (frontier.length > 0) {
      const next: string[] = [];
      for (const l of flow.links) {
        if (frontier.includes(l[from]) && !keep.has(l[to])) {
          keep.add(l[to]);
          next.push(l[to]);
        }
      }
      frontier = next;
    }
  };
  walk("source", "target");
  walk("target", "source");
  return keep;
}
