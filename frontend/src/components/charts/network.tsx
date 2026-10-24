"use client";

import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { useEffect, useMemo, useRef } from "react";
import type { GraphNode, Subgraph } from "@/lib/types";
import { useChartColors } from "@/lib/theme";

/**
 * Positions come from the backend (GraphNode.x/y) so the healthy and
 * perturbed graphs line up exactly. When they are missing, nodes are placed
 * in one column per region, which is deterministic and keeps both sides equal.
 */
function positions(nodes: GraphNode[]) {
  if (nodes.every((n) => n.x != null && n.y != null)) {
    return new Map(nodes.map((n) => [n.id, { x: n.x!, y: n.y! }]));
  }
  const groups = [...new Set(nodes.map((n) => n.group))];
  const rowIn = new Map<string, number>();
  return new Map(
    nodes.map((n) => {
      const col = groups.indexOf(n.group);
      const row = rowIn.get(n.group) ?? 0;
      rowIn.set(n.group, row + 1);
      return [n.id, { x: col * 160, y: row * 70 }];
    }),
  );
}

export function NetworkGraph({
  graph,
  variant,
  selectedId,
  onSelect,
}: {
  graph: Subgraph;
  variant: "healthy" | "perturbed";
  selectedId: string | null;
  onSelect: (node: GraphNode | null) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const c = useChartColors();
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const elements = useMemo<ElementDefinition[]>(() => {
    const pos = positions(graph.nodes);
    const groups = [...new Set(graph.nodes.map((n) => n.group))];
    return [
      ...groups.map((g) => ({ data: { id: `group:${g}`, label: g }, classes: "region", selectable: false })),
      ...graph.nodes.map((n) => ({
        data: { id: n.id, label: n.label, parent: `group:${n.group}`, impact: n.is_seed ? 1 : n.impact },
        position: pos.get(n.id),
        classes: n.is_seed ? "seed" : "",
      })),
      ...graph.edges.map((e, i) => ({
        data: { id: `e${i}`, source: e.source, target: e.target, weight: e.weight, lost: e.lost },
        classes: e.lost > 0 ? "lost" : "",
      })),
    ];
  }, [graph]);

  useEffect(() => {
    if (!el.current || !c) return;
    const perturbed = variant === "perturbed";
    const instance = cytoscape({
      container: el.current,
      elements,
      layout: { name: "preset", fit: true, padding: 36 },
      minZoom: 0.3,
      maxZoom: 3,
      wheelSensitivity: 0.2,
      autoungrabify: true,
      boxSelectionEnabled: false,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "font-family": getComputedStyle(document.body).fontFamily,
            "font-size": 10,
            color: c["muted-foreground"],
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: perturbed ? "mapData(impact, 0, 1, 14, 30)" : 18,
            height: perturbed ? "mapData(impact, 0, 1, 14, 30)" : 18,
            // Downstream loss is drawn in ink, darker with impact; orange stays reserved for the seeds.
            "background-color": perturbed ? `mapData(impact, 0, 1, ${c.card}, ${c["muted-foreground"]})` : c.card,
            "border-width": 1.5,
            "border-color": c["muted-foreground"],
            "overlay-opacity": 0,
          },
        },
        {
          selector: "node.seed",
          style: perturbed
            ? { "background-color": c.seed, "border-color": c.foreground, "border-width": 2, "border-style": "dashed", opacity: 0.85 }
            : { "border-color": c.seed, "border-width": 3 },
        },
        {
          selector: "node.region",
          style: {
            label: "data(label)",
            "text-valign": "top",
            "text-halign": "center",
            "text-margin-y": -4,
            "font-size": 10,
            "font-family": getComputedStyle(document.body).fontFamily,
            color: c.faint,
            "background-color": c.chance,
            "background-opacity": 0.45,
            "border-width": 1,
            "border-color": c.border,
            shape: "round-rectangle",
            padding: "18px",
          },
        },
        {
          selector: "node:selected",
          style: { "border-color": c.signal, "border-width": 3, "border-style": "solid" },
        },
        {
          selector: "edge",
          style: {
            width: "mapData(weight, 0, 0.5, 1, 5)",
            "line-color": c.faint,
            "target-arrow-color": c.faint,
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.8,
            "curve-style": "bezier",
            opacity: 0.7,
          },
        },
        ...(perturbed
          ? [
              {
                selector: "edge.lost",
                style: {
                  "line-color": c.foreground,
                  "target-arrow-color": c.foreground,
                  "line-style": "dashed" as const,
                  "line-dash-pattern": [6, 4],
                  opacity: "mapData(lost, 0, 0.5, 0.45, 1)" as unknown as number,
                },
              },
            ]
          : []),
      ],
    });
    instance.on("tap", "node", (evt) => {
      const n = evt.target;
      if (n.hasClass("region")) return;
      onSelectRef.current(graph.nodes.find((g) => g.id === n.id()) ?? null);
    });
    instance.on("tap", (evt) => {
      if (evt.target === instance) onSelectRef.current(null);
    });
    cy.current = instance;
    const ro = new ResizeObserver(() => {
      instance.resize();
      instance.fit(undefined, 36);
    });
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      instance.destroy();
      cy.current = null;
    };
  }, [elements, c, variant, graph.nodes]);

  // Selection is mirrored across both graphs without rebuilding them.
  useEffect(() => {
    const inst = cy.current;
    if (!inst) return;
    inst.$("node:selected").unselect();
    if (selectedId) inst.$id(selectedId).select();
  }, [selectedId, elements, c]);

  return <div ref={el} className="h-full w-full" />;
}
