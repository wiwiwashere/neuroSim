"use client";

import { useMemo } from "react";
import type { GroupScore, SankeyLink } from "@/lib/types";
import { useChartColors, withAlpha } from "@/lib/theme";
import ChartPlot, { baseLayout } from "./plot";

/**
 * Seed clusters (left) to super regions (right). Seeds wear --seed; a region
 * wears --signal only when it is above chance, so colour on the right side
 * means "real effect", never just "a region".
 */
export function DamageSankey({ links, groups }: { links: SankeyLink[]; groups: GroupScore[] }) {
  const c = useChartColors();

  const data = useMemo(() => {
    if (!c) return null;
    const sources = [...new Set(links.map((l) => l.source))];
    const targetTotals = new Map<string, number>();
    for (const l of links) targetTotals.set(l.target, (targetTotals.get(l.target) ?? 0) + l.value);
    const targets = [...targetTotals.keys()].sort((a, b) => targetTotals.get(b)! - targetTotals.get(a)!);
    const labels = [...sources, ...targets];
    const index = new Map(labels.map((l, i) => [l, i]));
    const byGroup = new Map(groups.map((g) => [g.group, g]));

    const targetColor = (t: string) => (byGroup.get(t)?.above_chance ? c.signal : c.faint);
    const nodeColors = [...sources.map(() => c.seed), ...targets.map(targetColor)];
    const custom = labels.map((l) => {
      const g = byGroup.get(l);
      if (!g) return "seed cluster";
      return `${g.function_label ?? ""}<br>z = ${g.z_score.toFixed(1)} · ${g.above_chance ? "above chance" : "within chance"}`;
    });

    return [
      {
        type: "sankey" as const,
        arrangement: "fixed" as const,
        valueformat: ".1f",
        node: {
          label: labels,
          color: nodeColors,
          customdata: custom,
          hovertemplate: "<b>%{label}</b><br>%{customdata}<br>impact %{value}<extra></extra>",
          pad: 22,
          thickness: 14,
          line: { width: 0 },
        },
        link: {
          source: links.map((l) => index.get(l.source)!),
          target: links.map((l) => index.get(l.target)!),
          value: links.map((l) => l.value),
          color: links.map((l) => withAlpha(targetColor(l.target), byGroup.get(l.target)?.above_chance ? 0.32 : 0.22)),
          hovertemplate: "%{source.label} → %{target.label}<br>summed impact %{value}<extra></extra>",
        },
        textfont: { color: c.foreground, size: 13 },
      },
    ];
  }, [links, groups, c]);

  if (!c || !data) return <div className="h-full animate-pulse rounded-md bg-muted/60" />;
  return <ChartPlot data={data} layout={baseLayout(c, { margin: { l: 4, r: 4, t: 8, b: 8 } })} />;
}
