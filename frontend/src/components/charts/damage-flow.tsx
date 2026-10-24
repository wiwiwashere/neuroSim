"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { buildFlow, connectedRows, type FlowGrouping, type FlowRow } from "@/lib/flow";
import type { GraphNode, Subgraph } from "@/lib/types";
import { cn } from "@/lib/utils";

const ROW_H = 40;
const ROW_GAP = 8;
const HEAD_H = 28;
const BOX_W = 190;
const MIN_COL_W = 170;
const MAX_STROKE = 14;

/**
 * The perturbed subgraph as a left-to-right flow: seeds, then one column per
 * synapse away. Grey width is the connection, orange width the drive the
 * perturbation removes from it, so the loss is seen thinning out downstream.
 * Rows the Ranked tab calls above chance are blue.
 */
export function DamageFlow({
  graph,
  grouping,
  aboveChance,
  selectedId,
  onSelect,
}: {
  graph: Subgraph;
  grouping: FlowGrouping;
  /** Cell types or regions that beat the random-DA baseline. */
  aboveChance: Set<string>;
  selectedId: string | null;
  onSelect: (node: GraphNode | null) => void;
}) {
  const flow = useMemo(() => buildFlow(graph, grouping), [graph, grouping]);
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);

  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const nCols = flow.columns.length;
  const colW = Math.max(MIN_COL_W, width / Math.max(nCols, 1));
  const innerW = Math.floor(colW * nCols);
  const boxW = Math.min(BOX_W, colW - 28);
  const maxRows = Math.max(...flow.columns.map((c) => c.rows.length), 1);
  const height = HEAD_H + maxRows * (ROW_H + ROW_GAP) + 8;

  const place = useMemo(() => {
    const at = new Map<string, { x: number; y: number }>();
    flow.columns.forEach((c, i) => c.rows.forEach((r, j) => at.set(r.key, { x: i * colW + 12, y: HEAD_H + j * (ROW_H + ROW_GAP) })));
    return at;
  }, [flow, colW]);

  // Links leave and enter a row at spread-out points, ordered by where they go,
  // so a row with many links fans out instead of meeting in one spike.
  const ports = useMemo(() => {
    const y = (key: string) => place.get(key)!.y;
    const at = new Map<string, { y1: number; y2: number }>();
    const spread = (links: typeof flow.links, end: "source" | "target", other: "source" | "target") => {
      const byRow = new Map<string, typeof flow.links>();
      for (const l of links) byRow.set(l[end], [...(byRow.get(l[end]) ?? []), l]);
      for (const [row, ls] of byRow) {
        ls.sort((a, b) => y(a[other]) - y(b[other]));
        const step = Math.min(4, (ROW_H - 12) / Math.max(ls.length - 1, 1));
        ls.forEach((l, i) => {
          const k = `${l.source}->${l.target}`;
          const p = at.get(k) ?? { y1: 0, y2: 0 };
          p[end === "source" ? "y1" : "y2"] = y(row) + ROW_H / 2 + (i - (ls.length - 1) / 2) * step;
          at.set(k, p);
        });
      }
    };
    spread(flow.links, "source", "target");
    spread(flow.links, "target", "source");
    return at;
  }, [flow, place]);

  const selectedRow = flow.columns.flatMap((c) => c.rows).find((r) => r.nodes.some((n) => n.id === selectedId))?.key ?? null;
  const focus = hovered ?? pinned;
  const lit = useMemo(() => (focus ? connectedRows(flow, focus) : null), [flow, focus]);
  const maxWeight = Math.max(...flow.links.map((l) => l.weight), 1e-9);
  const downstream = flow.columns.flatMap((c) => c.rows).filter((r) => !r.isSeed);
  const maxImpact = Math.max(...downstream.map((r) => r.impact), 1e-9);
  // The row holding the single most hit neuron, which is also what the detail panel opens on.
  const hardest = [...downstream].sort((a, b) => b.nodes[0].impact - a.nodes[0].impact)[0];
  const hardestColumn = hardest ? flow.columns[hardest.column].title.toLowerCase() : "";

  return (
    <div className="grid gap-3">
      {hardest && (
        <p className="px-3 text-[14px] text-muted-foreground">
          Hardest-hit neuron: {grouping === "cell_type" && hardest.nodes.length > 1 ? "a " : ""}
          <span className={cn("font-mono font-medium", aboveChance.has(hardest.nodes[0].label) ? "text-signal" : "text-foreground")}>
            {hardest.nodes[0].label}
          </span>
          {grouping === "cell_type" && hardest.nodes.length > 1 && <> (one of {hardest.nodes.length})</>} in {hardest.nodes[0].group},{" "}
          {hardestColumn.startsWith("further") ? "reached indirectly" : hardestColumn}, impact {hardest.nodes[0].impact.toFixed(2)}. Read
          left to right: each column is one more synapse from the seeds, and the orange band is the input that goes missing.
        </p>
      )}
      <div ref={box} className="w-full min-w-0 overflow-x-auto">
        <div className="relative" style={{ width: innerW, height }} onMouseLeave={() => setHovered(null)}>
          {flow.columns.map((c, i) => (
            <div key={c.title} className="absolute top-0 text-[11.5px] text-muted-foreground" style={{ left: i * colW + 12, width: boxW }}>
              {c.title}
            </div>
          ))}

          <svg className="pointer-events-none absolute inset-0" width={innerW} height={height}>
            {flow.links.map((l) => {
              const s = place.get(l.source)!;
              const t = place.get(l.target)!;
              const x1 = s.x + boxW;
              const x2 = t.x;
              const { y1, y2 } = ports.get(`${l.source}->${l.target}`)!;
              const mx = (x1 + x2) / 2;
              const d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
              const on = !lit || (lit.has(l.source) && lit.has(l.target));
              return (
                <g key={`${l.source}->${l.target}`} style={{ opacity: on ? 1 : 0.12, transition: "opacity 150ms" }}>
                  <path
                    d={d}
                    fill="none"
                    stroke="var(--faint)"
                    strokeOpacity={0.35}
                    strokeWidth={Math.max(1, (MAX_STROKE * l.weight) / maxWeight)}
                  />
                  {l.lost > 0 && (
                    <path
                      d={d}
                      fill="none"
                      stroke="var(--seed)"
                      strokeOpacity={0.8}
                      strokeWidth={Math.max(1, (MAX_STROKE * l.lost) / maxWeight)}
                    />
                  )}
                </g>
              );
            })}
          </svg>

          {flow.columns.flatMap((c) =>
            c.rows.map((r) => (
              <Row
                key={r.key}
                row={r}
                style={{ left: place.get(r.key)!.x, top: place.get(r.key)!.y, width: boxW, height: ROW_H }}
                grouped={grouping === "cell_type"}
                above={aboveChance.has(r.label) || aboveChance.has(r.region)}
                barShare={r.isSeed ? 1 : r.impact / maxImpact}
                dimmed={!!lit && !lit.has(r.key)}
                selected={r.key === selectedRow}
                onHover={setHovered}
                onSelect={() => {
                  setPinned(r.key === pinned ? null : r.key);
                  onSelect(r.key === selectedRow ? null : r.nodes[0]);
                }}
              />
            )),
          )}
        </div>
        {flow.hiddenEdges > 0 && (
          <p className="px-3 pb-1 text-[11.5px] text-faint">
            {flow.hiddenEdges} feedback or same-step connection{flow.hiddenEdges === 1 ? "" : "s"} not drawn.
          </p>
        )}
      </div>
    </div>
  );
}

function Row({
  row,
  style,
  grouped,
  above,
  barShare,
  dimmed,
  selected,
  onHover,
  onSelect,
}: {
  row: FlowRow;
  style: React.CSSProperties;
  grouped: boolean;
  above: boolean;
  barShare: number;
  dimmed: boolean;
  selected: boolean;
  onHover: (key: string | null) => void;
  onSelect: () => void;
}) {
  const n = row.nodes.length;
  return (
    <button
      type="button"
      onMouseEnter={() => onHover(row.key)}
      onFocus={() => onHover(row.key)}
      onBlur={() => onHover(null)}
      onClick={onSelect}
      title={`${row.label} · ${row.region}${n > 1 ? ` · ${n} neurons` : ""}${row.isSeed ? "" : ` · mean impact ${row.impact.toFixed(2)}`}`}
      className={cn(
        "absolute flex flex-col justify-center gap-1 rounded-md border bg-card px-2.5 text-left transition-opacity duration-150",
        row.isSeed && "border-seed/60 bg-seed-soft",
        row.isMore && "border-dashed",
        selected && "ring-2 ring-signal",
        dimmed && "opacity-35",
      )}
      style={style}
    >
      <span className="flex items-baseline gap-1.5 text-[12px] leading-none">
        <span className={cn("truncate font-mono", row.isMore ? "text-muted-foreground" : "font-medium", above && "text-signal")}>
          {row.label}
        </span>
        {grouped && n > 1 && !row.isMore && <span className="font-mono text-[11px] text-muted-foreground">×{n}</span>}
        <span className="ml-auto shrink-0 font-mono text-[11px] text-muted-foreground tabular">
          {row.isSeed ? "seed" : row.impact.toFixed(2)}
        </span>
      </span>
      <span className="flex items-center gap-1.5">
        <span className="relative h-[3px] flex-1 overflow-hidden rounded-full bg-muted">
          <span
            className={cn("absolute inset-y-0 left-0 rounded-full", row.isSeed ? "bg-seed" : above ? "bg-signal" : "bg-foreground/70")}
            style={{ width: `${Math.max(2, barShare * 100)}%` }}
          />
        </span>
        <span className="max-w-[45%] truncate text-[10.5px] leading-none text-faint">{row.region}</span>
      </span>
    </button>
  );
}
