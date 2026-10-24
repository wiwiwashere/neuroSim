"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, codexUrl } from "@/lib/api";
import { int, LEVEL_LABEL, pct, SCOPE_LINE, zPhrase } from "@/lib/format";
import type { GraphNode, GroupLevel, GroupScore, SimulationResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { runLabel, type Tab, useWorkspace } from "@/lib/workspace";
import { CompareTab } from "./compare";
import { RunCta } from "./perturbation";
import { EmptyState, ErrorNote, StatTile } from "./primitives";
import { RunSummaryCard } from "./run-summary";

const DamageSankey = dynamic(() => import("@/components/charts/sankey").then((m) => m.DamageSankey), { ssr: false });
const RankedBars = dynamic(() => import("@/components/charts/ranked-bars").then((m) => m.RankedBars), { ssr: false });
const NetworkGraph = dynamic(() => import("@/components/charts/network").then((m) => m.NetworkGraph), { ssr: false });

export const LEVELS: GroupLevel[] = ["super_region", "region", "cell_type"];

export function groupsAt(result: SimulationResult, level: GroupLevel): GroupScore[] {
  return result.groups[level] ?? [];
}

function Panel({ title, aside, children, className }: { title?: string; aside?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border bg-card", className)}>
      {title && (
        <div className="flex items-center justify-between gap-3 border-b px-4 py-2.5">
          <h3 className="text-[13px] font-medium">{title}</h3>
          {aside}
        </div>
      )}
      {children}
    </div>
  );
}

// --- Overview ---------------------------------------------------------------

function Overview({ result }: { result: SimulationResult }) {
  const sankey = useQuery({ queryKey: ["sankey", result.run_id], queryFn: () => api.sankey(result.run_id) });
  const supers = groupsAt(result, "super_region");
  const top = [...supers].sort((a, b) => b.z_score - a.z_score).slice(0, 3);
  const ratio = result.disruption_null_mean > 0 ? result.disruption_score / result.disruption_null_mean : null;

  return (
    <div className="grid gap-4">
      {/* One panel: the headline number, what it is measured against, and where it goes. */}
      <Panel className="landed">
        <div className="grid gap-5 border-b px-5 pt-5 pb-4 md:grid-cols-[auto_1fr] md:items-end md:gap-10">
          {/* Lead with the comparison to chance: that is the claim, the raw percent is not. */}
          <div className="flex flex-col gap-1">
            <span className="text-[13px] font-medium">{runLabel(result.request)}</span>
            <span className="text-[44px] leading-none font-semibold tracking-[-0.02em] tabular">
              {ratio !== null ? `${ratio.toFixed(1)}×` : pct(result.disruption_score)}
              {ratio !== null && <span className="ml-2 text-[20px] font-medium text-muted-foreground">chance</span>}
            </span>
            <span className={cn("text-[13px]", result.disruption_z >= 2 ? "font-medium text-signal" : "text-muted-foreground")}>
              z {result.disruption_z.toFixed(1)}, {zPhrase(result.disruption_z)}
            </span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 md:max-w-xl md:justify-self-end">
            <Compared label={`${result.request.human_gene} seeds`} value={pct(result.disruption_score)} strong />
            <Compared label="Random DA neurons, same count" value={pct(result.disruption_null_mean)} />
            <p className="text-[12px] text-muted-foreground sm:col-span-2">
              Share of downstream input lost. {int(result.n_seed_neurons)} seed neurons perturbed, {int(result.n_reached)} reached within{" "}
              {result.assumptions.hops ?? 3} synapses.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-3.5">
          <h3 className="text-[13px] font-semibold">Where does the damage go?</h3>
          <span className="flex items-center gap-3 text-[11.5px] text-muted-foreground">
            <Legend swatch="bg-seed" label="seed cluster" />
            <Legend swatch="bg-signal" label="above chance" />
            <Legend swatch="bg-faint" label="within chance" />
          </span>
        </div>
        <div className="h-[340px] px-2 py-2">
          {sankey.error && <ErrorNote error={sankey.error} />}
          {sankey.data && <DamageSankey links={sankey.data} groups={supers} />}
        </div>
      </Panel>

      <RunSummaryCard result={result} />

      {top.length > 0 && (
        <Panel title="Most dependent regions">
          <ol className="divide-y">
            {top.map((g, i) => (
              <li key={g.group} className="grid grid-cols-[1.5rem_1fr_auto] items-baseline gap-3 px-4 py-2.5 text-[13px]">
                <span className="font-mono text-[11px] text-faint">{i + 1}</span>
                <span>
                  <span className="font-medium">{g.group}</span>
                  {g.function_label && <span className="text-muted-foreground"> · {g.function_label}</span>}
                </span>
                <span className={cn("font-mono tabular", g.above_chance ? "text-signal" : "text-muted-foreground")}>
                  z {g.z_score.toFixed(1)} <span className="text-[11px]">{g.above_chance ? "above chance" : "chance"}</span>
                </span>
              </li>
            ))}
          </ol>
        </Panel>
      )}
    </div>
  );
}

/** Two numbers at equal weight so the gap is seen, not read. */
function Compared({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={cn("rounded-lg border px-3 py-2", strong ? "border-foreground/25" : "border-dashed")}>
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <div className={cn("text-[22px] leading-tight tabular", strong ? "font-semibold" : "font-medium text-muted-foreground")}>{value}</div>
    </div>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("size-2.5 rounded-[3px]", swatch)} />
      {label}
    </span>
  );
}

// --- Ranked -----------------------------------------------------------------

export function LevelToggle({ value, onChange, available }: { value: GroupLevel; onChange: (l: GroupLevel) => void; available?: Set<string> }) {
  return (
    <ToggleGroup type="single" value={value} onValueChange={(v) => v && onChange(v as GroupLevel)} variant="outline" size="sm">
      {LEVELS.map((l) => (
        <ToggleGroupItem key={l} value={l} className="h-7 px-2.5 text-[12px]" disabled={available && !available.has(l)}>
          {LEVEL_LABEL[l]}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

function Ranked({ result }: { result: SimulationResult }) {
  const ws = useWorkspace();
  const groups = groupsAt(result, ws.level);
  const available = new Set(Object.keys(result.groups));
  const [showTable, setShowTable] = useState(false);

  return (
    <Panel
      title="Which effects are real, and which are chance?"
      aside={<LevelToggle value={ws.level} onChange={(level) => ws.set({ level })} available={available} />}
    >
      {groups.length === 0 ? (
        <EmptyState title={`No ${LEVEL_LABEL[ws.level].toLowerCase()} scores in this run`}>
          The engine didn’t return this level yet. Try super region.
        </EmptyState>
      ) : (
        <>
          <div className="px-2 pt-2" style={{ height: Math.max(240, groups.length * 58 + 80) }}>
            <RankedBars groups={groups} />
          </div>
          <div className="flex items-center justify-between border-t px-4 py-2 text-[12px] text-muted-foreground">
            <span>
              Blue bars pass the false-discovery test (q &lt; 0.05). The grey band is where random dopamine neurons land 95% of the time.
            </span>
            <button className="shrink-0 underline-offset-2 hover:underline" onClick={() => setShowTable((s) => !s)}>
              {showTable ? "Hide table" : "Show table"}
            </button>
          </div>
          {showTable && <GroupTable groups={groups} />}
        </>
      )}
    </Panel>
  );
}

function GroupTable({ groups }: { groups: GroupScore[] }) {
  return (
    <div className="overflow-x-auto border-t">
      <table className="w-full text-[12.5px]">
        <thead className="text-left text-[11.5px] text-muted-foreground">
          <tr className="border-b">
            {["Group", "Function", "Neurons", "Strong hits", "Direct %", "z", "q", ""].map((h) => (
              <th key={h} className="px-4 py-2 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mono tabular">
          {groups.map((g) => (
            <tr key={g.group} className="border-b last:border-0">
              <td className="px-4 py-1.5 font-sans">{g.group}</td>
              <td className="px-4 py-1.5 font-sans text-muted-foreground">{g.function_label}</td>
              <td className="px-4 py-1.5">{int(g.n_neurons)}</td>
              <td className="px-4 py-1.5">{int(g.n_strong_hits)}</td>
              <td className="px-4 py-1.5">{(g.mean_direct * 100).toFixed(2)}</td>
              <td className="px-4 py-1.5">{g.z_score.toFixed(2)}</td>
              <td className="px-4 py-1.5">{g.q_value.toFixed(3)}</td>
              <td className="px-4 py-1.5 font-sans text-[11.5px] whitespace-nowrap">{g.above_chance ? <span className="text-signal">above chance</span> : "chance"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Network ----------------------------------------------------------------

function Network({ result }: { result: SimulationResult }) {
  const graph = useQuery({ queryKey: ["subgraph", result.run_id], queryFn: () => api.subgraph(result.run_id) });
  const [picked, setPicked] = useState<GraphNode | null | undefined>(undefined);
  const mostHit = useMemo(
    () => graph.data?.nodes.filter((n) => !n.is_seed).sort((x, y) => y.impact - x.impact)[0] ?? null,
    [graph.data],
  );
  const selected = picked === undefined ? mostHit : picked;
  const setSelected = setPicked;
  const gene = result.request.human_gene;
  const perturbLabel = result.request.mode === "reduce_output" ? `output −${Math.round((result.request.strength ?? 1) * 100)}%` : "knockout";

  return (
    <div className="grid gap-4">
      <div className="grid gap-4 md:grid-cols-2">
        {(["healthy", "perturbed"] as const).map((variant) => (
          <Panel
            key={variant}
            title={variant === "healthy" ? "Healthy" : `With ${gene} ${perturbLabel}`}
            aside={
              variant === "perturbed" ? (
                <span className="flex shrink-0 items-center gap-3 text-[11.5px] whitespace-nowrap text-muted-foreground">
                  <Legend swatch="bg-seed" label="seed" />
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-4 border-t-2 border-dashed border-foreground" />
                    lost drive
                  </span>
                </span>
              ) : (
                <span className="text-[11.5px] text-muted-foreground">
                  {graph.data ? `${graph.data.nodes.length} neurons · ${graph.data.edges.length} connections` : ""}
                </span>
              )
            }
          >
            <div className="h-[380px]">
              {graph.error && <ErrorNote error={graph.error} />}
              {graph.data && (
                <NetworkGraph graph={graph.data} variant={variant} selectedId={selected?.id ?? null} onSelect={setSelected} />
              )}
            </div>
          </Panel>
        ))}
      </div>
      {selected ? (
        <NeuronDetail node={selected} result={result} onClose={() => setSelected(null)} />
      ) : (
        <p className="px-1 text-[12.5px] text-muted-foreground">
          Same neurons, same positions. Click a neuron to see the paths that carry the loss to it.
        </p>
      )}
    </div>
  );
}

function NeuronDetail({ node, result, onClose }: { node: GraphNode; result: SimulationResult; onClose: () => void }) {
  // Subgraph ids are strings; explain needs a FlyWire root id. Use the id when
  // it is one, else match the node's cell type against the run's top neurons.
  const rootId = useMemo(() => {
    if (/^\d{6,}$/.test(node.id)) return Number(node.id);
    return result.top_neurons.find((n) => n.cell_type === node.label)?.root_id ?? null;
  }, [node, result]);
  const explain = useQuery({
    queryKey: ["explain", result.run_id, rootId],
    queryFn: () => api.explain(result.run_id, rootId!),
    enabled: rootId != null && !node.is_seed,
  });

  return (
    <Panel
      title={`${node.label} · ${node.group}`}
      aside={
        <button onClick={onClose} aria-label="Close" className="text-muted-foreground hover:text-foreground">
          <X className="size-4" />
        </button>
      }
    >
      <div className="grid grid-cols-[auto_1fr_auto] items-start gap-6 px-4 py-3 text-[13px]">
        <StatTile label={node.is_seed ? "Seed neuron" : "Impact"} value={node.is_seed ? "—" : node.impact.toFixed(2)} />
        <div>
          <p className="mb-1.5 text-[12px] text-muted-foreground">Strongest paths from the seeds</p>
          {node.is_seed && <p className="text-muted-foreground">This is one of the perturbed neurons.</p>}
          {!node.is_seed && rootId == null && <p className="text-muted-foreground">No root id for this neuron in the run.</p>}
          {explain.error && <ErrorNote error={explain.error} />}
          <ul className="grid gap-1.5">
            {explain.data?.paths.map((p, i) => (
              <li key={i} className="flex items-center gap-3">
                <span className="font-mono text-[12.5px]">{p.neurons.join(" → ")}</span>
                <span className="font-mono text-[11.5px] text-muted-foreground">{p.strength.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </div>
        {rootId != null && (
          <a
            href={codexUrl(rootId)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] hover:bg-secondary"
          >
            View in Codex (3D)
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>
    </Panel>
  );
}

// --- Tabs -------------------------------------------------------------------

export function Results() {
  const ws = useWorkspace();
  const result = ws.activeRun?.result;
  // Warm the other views as soon as a run lands, so tab switches are instant.
  const id = result?.run_id ?? "";
  useQuery({ queryKey: ["sankey", id], queryFn: () => api.sankey(id), enabled: !!result });
  useQuery({ queryKey: ["subgraph", id], queryFn: () => api.subgraph(id), enabled: !!result });

  return (
    <Tabs value={ws.tab} onValueChange={(v) => ws.set({ tab: v as Tab })} className="flex h-full min-h-0 flex-col gap-0">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-4 py-2.5 sm:px-6">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="ranked">Ranked</TabsTrigger>
          <TabsTrigger value="network">Network</TabsTrigger>
          <TabsTrigger value="compare">Compare</TabsTrigger>
        </TabsList>
        <RunSwitcher />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
        {!result && ws.tab !== "compare" ? (
          <EmptyState title={ws.gene ? `Ready to perturb ${ws.gene}` : "No run yet"}>
            {ws.gene
              ? "Run it here or from the left, or ask the agent a what-if."
              : "Pick a disease and a gene on the left, or ask the agent on the right."}
            <RunCta />
          </EmptyState>
        ) : (
          <>
            {/* Keyed on the run so a new result (yours or the agent's) visibly lands. */}
            <TabsContent value="overview" key={`o-${ws.activeKey}`} className="animate-in fade-in duration-200">
              {result && <Overview result={result} />}
            </TabsContent>
            <TabsContent value="ranked" key={`r-${ws.activeKey}`} className="animate-in fade-in duration-200">
              {result && <Ranked result={result} />}
            </TabsContent>
            <TabsContent value="network" key={`n-${ws.activeKey}`} className="animate-in fade-in duration-200">
              {result && <Network result={result} />}
            </TabsContent>
            <TabsContent value="compare">
              <CompareTab />
            </TabsContent>
          </>
        )}
        <p className="mt-6 text-center text-[11.5px] text-faint">{SCOPE_LINE}</p>
      </div>
    </Tabs>
  );
}

function RunSwitcher() {
  const ws = useWorkspace();
  if (ws.runs.length === 0) return null;
  return (
    <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
      Showing
      <select
        value={ws.activeKey ?? ""}
        onChange={(e) => ws.set({ activeKey: e.target.value })}
        className="h-7 rounded-md border bg-card px-2 font-mono text-[12px] text-foreground"
      >
        {ws.runs.map((r) => (
          <option key={r.key} value={r.key}>
            {r.label}
            {r.source === "agent" ? "  (agent)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
