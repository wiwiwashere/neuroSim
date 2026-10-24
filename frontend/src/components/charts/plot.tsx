"use client";

// Plotly only runs in the browser. This wrapper loads the minified bundle
// once, on the client, and applies the shared chart chrome (fonts, recessive
// grid, transparent paper) so every chart looks like one system.

import dynamic from "next/dynamic";
import type { Config, Layout } from "plotly.js";
import type { PlotParams } from "react-plotly.js";
import type { ChartColors } from "@/lib/theme";

const Plot = dynamic(
  async () => {
    const [{ default: Plotly }, { default: createPlotlyComponent }] = await Promise.all([
      import("plotly.js-dist-min"),
      import("react-plotly.js/factory"),
    ]);
    return createPlotlyComponent(Plotly);
  },
  { ssr: false, loading: () => <div className="h-full w-full animate-pulse rounded-md bg-muted/60" /> },
);

export const plotConfig: Partial<Config> = { displayModeBar: false, responsive: true };

// next/font renames the family, so read the resolved stack off <body>.
const family = () =>
  typeof document === "undefined" ? "system-ui, sans-serif" : getComputedStyle(document.body).fontFamily;

export function baseLayout(c: ChartColors, extra: Partial<Layout> = {}): Partial<Layout> {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: family(), size: 12, color: c["muted-foreground"] },
    hoverlabel: {
      bgcolor: c.card,
      bordercolor: c.border,
      font: { family: family(), size: 12, color: c.foreground },
      align: "left",
    },
    margin: { l: 8, r: 8, t: 8, b: 8 },
    ...extra,
  };
}

export default function ChartPlot(props: PlotParams) {
  return <Plot useResizeHandler style={{ width: "100%", height: "100%" }} config={plotConfig} {...props} />;
}
