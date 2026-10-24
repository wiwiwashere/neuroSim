"use client";

import { useMemo } from "react";
import type { GroupScore } from "@/lib/types";
import { useChartColors } from "@/lib/theme";
import ChartPlot, { baseLayout } from "./plot";

// Random DA seed sets land inside ±1.96 standard deviations 95% of the time.
export const CHANCE_Z = 1.96;

/**
 * Vulnerability per group as a z-score against random dopamine neurons.
 * The grey band is what chance looks like; bars outside it in --signal are
 * the groups that pass the FDR test (above_chance), everything else stays ink.
 */
export function RankedBars({ groups, highlight }: { groups: GroupScore[]; highlight?: Set<string> }) {
  const c = useChartColors();
  const rows = useMemo(() => [...groups].sort((a, b) => a.z_score - b.z_score), [groups]); // Plotly draws bottom-up

  if (!c) return <div className="h-full animate-pulse rounded-md bg-muted/60" />;

  const zs = rows.map((g) => g.z_score);
  const lo = Math.min(-CHANCE_Z - 0.6, ...zs) - 0.4;
  const hi = Math.max(CHANCE_Z + 0.6, ...zs) + 0.8;
  const tick = (g: GroupScore) => {
    const name = highlight?.has(g.group) ? `<b>${g.group}</b>` : g.group;
    return g.function_label ? `${name}<br><span style="color:${c.faint};font-size:11px">${g.function_label}</span>` : name;
  };

  return (
    <ChartPlot
      data={[
        {
          type: "bar",
          orientation: "h",
          x: zs,
          y: rows.map((g) => g.group),
          marker: {
            color: rows.map((g) => (g.above_chance ? c.signal : c.faint)),
            line: { width: 0 },
          },
          text: rows.map((g) => `z ${g.z_score >= 0 ? "" : "−"}${Math.abs(g.z_score).toFixed(1)}`),
          textposition: "outside",
          cliponaxis: false,
          textfont: { color: c["muted-foreground"], size: 11.5 },
          customdata: rows.map((g) => [
            g.function_label ?? "",
            g.above_chance ? "above chance" : "within chance",
            g.q_value.toFixed(3),
            g.n_neurons.toLocaleString(),
            g.n_strong_hits.toLocaleString(),
            (g.mean_direct * 100).toFixed(2),
          ]),
          hovertemplate:
            "<b>%{y}</b> · %{customdata[0]}<br>" +
            "z = %{x:.2f} (%{customdata[1]}, q = %{customdata[2]})<br>" +
            "direct dependency %{customdata[5]}% · %{customdata[4]} strongly hit of %{customdata[3]}<extra></extra>",
          width: 0.56,
        },
      ]}
      layout={baseLayout(c, {
        margin: { l: 150, r: 24, t: 28, b: 36 },
        barcornerradius: 4,
        bargap: 0.3,
        showlegend: false,
        xaxis: {
          range: [lo, hi],
          zeroline: true,
          zerolinecolor: c.border,
          zerolinewidth: 1,
          gridcolor: c.border,
          griddash: "dot",
          tickfont: { size: 11, color: c.faint },
          title: { text: "z-score vs random dopamine neurons", font: { size: 11.5, color: c["muted-foreground"] }, standoff: 8 },
          fixedrange: true,
        },
        yaxis: {
          tickmode: "array",
          tickvals: rows.map((g) => g.group),
          ticktext: rows.map(tick),
          tickfont: { size: 12.5, color: c.foreground },
          ticks: "",
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
          {
            x: 0,
            y: 1,
            xref: "x",
            yref: "paper",
            yanchor: "bottom",
            text: "chance range",
            showarrow: false,
            font: { size: 11, color: c.faint },
          },
        ],
      })}
    />
  );
}
