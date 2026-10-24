"use client";

import { useMemo } from "react";
import type { GroupScore } from "@/lib/types";
import { useChartColors, useTheme } from "@/lib/theme";
import ChartPlot, { baseLayout } from "./plot";
import { CHANCE_Z } from "./ranked-bars";

// Gene B's identity colour: categorical slot 7 (violet), kept clear of
// --signal (above chance) and --seed (perturbed). Gene A wears the ink.
const GENE_B = { light: "#6250d6", dark: "#9085e9" };

/**
 * Two genes on one shared z axis: one row per region, a dot per gene, joined
 * by a line. Where the dots sit together the genes hit the region alike;
 * the shared chance band shows which of those hits are real.
 */
export function PairedDots({
  a,
  b,
  labelA,
  labelB,
  shared,
}: {
  a: GroupScore[];
  b: GroupScore[];
  labelA: string;
  labelB: string;
  shared: Set<string>;
}) {
  const c = useChartColors();
  const { theme } = useTheme();

  const rows = useMemo(() => {
    const byA = new Map(a.map((g) => [g.group, g]));
    const byB = new Map(b.map((g) => [g.group, g]));
    const names = [...new Set([...byA.keys(), ...byB.keys()])];
    const score = (n: string) => Math.max(byA.get(n)?.z_score ?? -Infinity, byB.get(n)?.z_score ?? -Infinity);
    return names
      .sort((x, y) => score(x) - score(y)) // Plotly draws bottom-up: strongest on top
      .map((n) => ({ name: n, a: byA.get(n), b: byB.get(n), fn: byA.get(n)?.function_label ?? byB.get(n)?.function_label }));
  }, [a, b]);

  if (!c) return <div className="h-full animate-pulse rounded-md bg-muted/60" />;
  const colorB = theme === "dark" ? GENE_B.dark : GENE_B.light;

  const zs = rows.flatMap((r) => [r.a?.z_score, r.b?.z_score]).filter((z): z is number => z != null);
  const lo = Math.min(-CHANCE_Z - 0.6, ...zs) - 0.4;
  const hi = Math.max(CHANCE_Z + 0.6, ...zs) + 0.8;
  const tick = (r: (typeof rows)[number]) => {
    const name = shared.has(r.name) ? `<b>${r.name}</b>` : r.name;
    return r.fn ? `${name}<br><span style="color:${c.faint};font-size:11px">${r.fn}</span>` : name;
  };
  const OFFSET = 0.14;
  const yOf = (i: number, key: "a" | "b") => i + (key === "a" ? OFFSET : -OFFSET);
  const dotTrace = (key: "a" | "b", label: string, color: string) => ({
    type: "scatter" as const,
    mode: "markers" as const,
    name: label,
    x: rows.map((r) => r[key]?.z_score ?? null),
    y: rows.map((_, i) => yOf(i, key)),
    text: rows.map((r) => r.name),
    marker: { size: 13, color, line: { width: 2, color: c.card } },
    customdata: rows.map((r) => [r[key]?.above_chance ? "above chance" : "within chance", r[key]?.q_value?.toFixed(3) ?? "—"]),
    hovertemplate: `<b>${label}</b> · %{text}<br>z = %{x:.2f} (%{customdata[0]}, q = %{customdata[1]})<extra></extra>`,
  });

  return (
    <ChartPlot
      data={[
        // Connectors first so the dots sit on top of them.
        ...rows.map((r, i) => ({
          type: "scatter" as const,
          mode: "lines" as const,
          x: [r.a?.z_score ?? null, r.b?.z_score ?? null],
          y: [yOf(i, "a"), yOf(i, "b")],
          line: { color: c.border, width: 3 },
          hoverinfo: "skip" as const,
          showlegend: false,
        })),
        dotTrace("a", labelA, c.foreground),
        dotTrace("b", labelB, colorB),
      ]}
      layout={baseLayout(c, {
        margin: { l: 150, r: 24, t: 36, b: 40 },
        showlegend: true,
        legend: { orientation: "h", x: 1, xanchor: "right", y: 1.02, yanchor: "bottom", font: { size: 12, color: c.foreground } },
        xaxis: {
          range: [lo, hi],
          zeroline: true,
          zerolinecolor: c.border,
          gridcolor: c.border,
          griddash: "dot",
          tickfont: { size: 11, color: c.faint },
          title: { text: "z-score vs random dopamine neurons", font: { size: 11.5, color: c["muted-foreground"] }, standoff: 8 },
          fixedrange: true,
        },
        yaxis: {
          tickmode: "array",
          tickvals: rows.map((_, i) => i),
          range: [-0.6, rows.length - 0.4],
          zeroline: false,
          showgrid: false,
          ticktext: rows.map(tick),
          tickfont: { size: 12.5, color: c.foreground },
          ticklabelstandoff: 10,
          fixedrange: true,
        },
        shapes: [
          {
            type: "rect",
            xref: "x",
            yref: "paper",
            x0: -CHANCE_Z,
            x1: CHANCE_Z,
            y0: 0,
            y1: 1,
            fillcolor: c.chance,
            line: { width: 0 },
            layer: "below",
          },
        ],
        annotations: [
          { x: 0, y: 1, xref: "x", yref: "paper", yanchor: "bottom", text: "chance range", showarrow: false, font: { size: 11, color: c.faint } },
        ],
      })}
    />
  );
}
