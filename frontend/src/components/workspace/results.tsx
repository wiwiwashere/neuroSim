"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, codexUrl } from "@/lib/api";
import type { FlowGrouping } from "@/lib/flow";
import { int, LEVEL_LABEL, pct, SCOPE_LINE, zPhrase } from "@/lib/format";
import type { GraphNode, GroupLevel, GroupScore, SimulationResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { type NetworkView, runLabel, type Tab, useWorkspace } from "@/lib/workspace";
import { DamageBars, regionShares } from "@/components/charts/damage-bars";
import { CompareTab } from "./compare";
import { RunCta } from "./perturbation";
import {
  EmptyState,
  ErrorNote,
  evidenceKey,
  ExpressionNote,
  StatTile,
  TierBadge,
  UploadedQuote,
  uniqueEvidence,
  UserSuppliedBadge,
  UserSuppliedNote,
} from "./primitives";
import { RunSummaryCard } from "./run-summary";

const RankedBars = dynamic(() => import("@/components/charts/ranked-bars").then((m) => m.RankedBars), { ssr: false });
const NetworkGraph = dynamic(() => import("@/components/charts/network").then((m) => m.NetworkGraph), { ssr: false });
const DamageFlow = dynamic(() => import("@/components/charts/damage-flow").then((m) => m.DamageFlow), { ssr: false });
const Network3D = dynamic(() => import("@/components/charts/network-3d").then((m) => m.Network3D), { ssr: false });

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
  const shares = useMemo(() => regionShares(sankey.data, supers), [sankey.data, supers]);
  const ratio = result.disruption_null_mean > 0 ? result.disruption_score / result.disruption_null_mean : null;
  const top = shares[0];

  return (
    <div className="grid gap-4">
      {result.seeds.user_supplied && (
        <p className="flex flex-wrap items-center gap-1.5 rounded-lg border border-dashed border-seed/60 bg-card px-4 py-2 text-[12px] leading-snug text-muted-foreground">
          <UserSuppliedBadge />
          The seeds come from a disease table someone added in this app. Nobody on the team has checked it, and the
          random baseline still draws dopamine neurons.
        </p>
      )}
      {/* One panel: the claim in a sentence, the two numbers behind it, then where it lands. */}
      <Panel className="landed">
        <div className="grid gap-5 border-b px-5 pt-5 pb-5 lg:grid-cols-[1fr_minmax(16rem,22rem)] lg:gap-10">
          <div className="flex flex-col gap-2">
            <span className="text-[12.5px] font-medium text-muted-foreground">{runLabel(result.request)}</span>
            <p className="text-[20px] leading-snug font-medium tracking-[-0.01em] text-balance">
              <Takeaway result={result} ratio={ratio} />
            </p>
            <p className="text-[14px] text-muted-foreground">
              That gap is {zPhrase(result.disruption_z)} (z {result.disruption_z.toFixed(1)})
              {result.disruption_z >= 2 ? "." : ", so treat it as noise."}
              {top && (
                <>
                  {" "}
                  Most of it lands on the <span className="font-medium text-foreground">{top.group}</span>
                  {top.score?.function_label && <> ({top.score.function_label})</>}: {Math.round(top.share * 100)}% of the total
                  {top.score ? (top.score.above_chance ? ", more than chance would put there." : ", but no more than chance would.") : "."}
                </>
              )}
            </p>
          </div>
          <div className="flex flex-col justify-end gap-2.5">
            <CompareBar label={`${result.request.human_gene} seeds`} value={result.disruption_score} max={Math.max(result.disruption_score, result.disruption_null_mean)} strong />
            <CompareBar label="Random DA neurons, same count" value={result.disruption_null_mean} max={Math.max(result.disruption_score, result.disruption_null_mean)} />
            <p className="text-[11.5px] text-muted-foreground">
              Share of all downstream input in the brain that is lost. {int(result.n_seed_neurons)} seed neurons, {int(result.n_reached)}{" "}
              neurons reached within {result.assumptions.hops ?? 3} synapses.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-baseline justify-between gap-3 px-5 pt-4">
          <h3 className="text-[13px] font-semibold">Where does the damage go?</h3>
          <span className="flex items-center gap-3 text-[11.5px] text-muted-foreground">
            <Legend swatch="bg-signal" label="hit harder than chance" />
            <Legend swatch="bg-faint/70" label="within chance" />
          </span>
        </div>
        <p className="px-5 pt-0.5 text-[12px] text-muted-foreground">Each bar is the region&apos;s share of all the input lost.</p>
        <div className="px-5 pt-4 pb-5">
          {sankey.error && <ErrorNote error={sankey.error} />}
          {shares.length > 0 && <DamageBars shares={shares} />}
        </div>
      </Panel>

      <EvidenceBehind result={result} />
      <RunSummaryCard result={result} />
    </div>
  );
}

/** The evidence rows these seeds rest on, with the ones approved from uploaded papers marked. */
function EvidenceBehind({ result }: { result: SimulationResult }) {
  const rows = uniqueEvidence(result.seeds);
  if (!rows.length) return null;
  const uploaded = rows.filter((r) => r.extracted).length;
  const supplied = rows.filter((r) => r.user_supplied).length;
  return (
    <Panel
      title="The evidence behind these seeds"
      aside={
        <span className="text-[11.5px] text-muted-foreground">
          {rows.length} row{rows.length > 1 ? "s" : ""}
          {uploaded ? ` · ${uploaded} from uploaded papers` : ""}
          {supplied ? ` · ${supplied} user-supplied` : ""}
        </span>
      }
    >
      <ul className="grid gap-2 px-4 py-3">
        {rows.map((e) => (
          <li key={evidenceKey(e)} className="grid gap-0.5 text-[12.5px] leading-snug">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span>
                <span className="font-mono">{e.clusters.join(", ")}</span>
                <span className="text-muted-foreground"> · {e.finding}</span>
              </span>
              <span className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
                {e.url ? (
                  <a href={e.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                    {e.citation}
                    <ExternalLink className="size-3" />
                  </a>
                ) : (
                  e.citation
                )}
                <TierBadge tier={e.tier} />
              </span>
            </div>
            <UploadedQuote row={e} />
            <UserSuppliedNote row={e} />
          </li>
        ))}
      </ul>
      {result.seeds.expression && (
        <div className="border-t px-4 py-3">
          <p className="mb-1 text-[12px] text-muted-foreground">Expression in fly neurons · atlas</p>
          <ExpressionNote
            expression={result.seeds.expression}
            seedClusters={[...new Set(result.seeds.seed_types.map((t) => t.cluster))]}
          />
        </div>
      )}
    </Panel>
  );
}

/** The run's claim as one sentence, in the words a first-time viewer would use. */
function Takeaway({ result, ratio }: { result: SimulationResult; ratio: number | null }) {
  const { human_gene: gene, mode, strength } = result.request;
  const verb = mode === "reduce_output" ? `Cutting ${gene} output by ${Math.round((strength ?? 1) * 100)}%` : `${gene} knockout`;
  const names = [...new Set(result.seeds.seed_types.map((t) => t.cluster))];
  const clusters = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : (names[0] ?? "");
  const n = int(result.n_seed_neurons);
  return (
    <>
      {verb} in {n} {clusters ? `${clusters} ` : ""}dopamine neurons removes{" "}
      {ratio !== null ? (
        <>
          <span className={cn("font-semibold", result.disruption_z >= 2 && "text-signal")}>{ratio.toFixed(1)}×</span> the downstream input that{" "}
          {n} random ones do.
        </>
      ) : (
        <>{pct(result.disruption_score)} of downstream input.</>
      )}
    </>
  );
}

/** Seeds against random neurons on one scale, so "2×" is seen as a longer bar, not read off two small percents. */
function CompareBar({ label, value, max, strong }: { label: string; value: number; max: number; strong?: boolean }) {
  return (
    <div className="grid gap-1">
      <div className="flex items-baseline justify-between text-[12px]">
        <span className={strong ? "font-medium" : "text-muted-foreground"}>{label}</span>
        <span className={cn("font-mono tabular", strong ? "font-semibold" : "text-muted-foreground")}>{pct(value)}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-[3px] bg-muted/70">
        <div
          className={cn("h-full rounded-[3px]", strong ? "bg-foreground/80" : "border border-dashed border-foreground/40 bg-transparent")}
          style={{ width: `${max > 0 ? (value / max) * 100 : 0}%` }}
        />
      </div>
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
  // The view lives in the workspace so the agent panel can tell the agent what is open.
  const { networkView: view, set: setWorkspace } = useWorkspace();
  const setView = (v: NetworkView) => setWorkspace({ networkView: v });
  const [grouping, setGrouping] = useState<FlowGrouping>("cell_type");
  const mostHit = useMemo(
    () => graph.data?.nodes.filter((n) => !n.is_seed).sort((x, y) => y.impact - x.impact)[0] ?? null,
    [graph.data],
  );
  // Cell types (or regions) the Ranked tab calls above chance are drawn blue here too.
  const aboveChance = useMemo(
    () => new Set([...groupsAt(result, "cell_type"), ...groupsAt(result, "region")].filter((g) => g.above_chance).map((g) => g.group)),
    [result],
  );
  const selected = picked === undefined ? mostHit : picked;
  const setSelected = setPicked;
  useEffect(() => {
    setWorkspace({
      selectedNeuron: selected ? { label: selected.label, region: selected.group, is_seed: selected.is_seed, impact: selected.impact } : null,
    });
  }, [selected, setWorkspace]);
  const gene = result.request.human_gene;
  const perturbLabel = result.request.mode === "reduce_output" ? `output −${Math.round((result.request.strength ?? 1) * 100)}%` : "knockout";
  const counts = graph.data ? `${graph.data.nodes.length} neurons · ${graph.data.edges.length} connections` : "";

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ToggleGroup type="single" value={view} onValueChange={(v) => v && setView(v as NetworkView)} variant="outline" size="sm">
          <ToggleGroupItem value="flow" className="h-7 px-2.5 text-[12px]">
            Flow by synapse
          </ToggleGroupItem>
          <ToggleGroupItem value="side_by_side" className="h-7 px-2.5 text-[12px]">
            Healthy vs perturbed
          </ToggleGroupItem>
          <ToggleGroupItem value="3d" className="h-7 px-2.5 text-[12px]">
            3D Connectome
          </ToggleGroupItem>
        </ToggleGroup>
        <span className="text-[11.5px] text-muted-foreground">{counts}</span>
      </div>

      {view === "flow" && (
        <Panel
          title={`How ${gene} ${perturbLabel} spreads, one synapse at a time`}
          aside={
            <div className="flex shrink-0 items-center gap-3">
              <span className="hidden items-center gap-3 text-[11.5px] whitespace-nowrap text-muted-foreground lg:flex">
                <Legend swatch="bg-seed" label="drive lost" />
                <Legend swatch="bg-faint/40" label="connection" />
                <Legend swatch="bg-signal" label="above chance" />
              </span>
              <ToggleGroup type="single" value={grouping} onValueChange={(v) => v && setGrouping(v as FlowGrouping)} variant="outline" size="sm">
                <ToggleGroupItem value="cell_type" className="h-7 px-2.5 text-[12px]">
                  Cell types
                </ToggleGroupItem>
                <ToggleGroupItem value="neuron" className="h-7 px-2.5 text-[12px]">
                  Neurons
                </ToggleGroupItem>
              </ToggleGroup>
            </div>
          }
        >
          <div className="px-1 pt-3 pb-2">
            {graph.error && <ErrorNote error={graph.error} />}
            {graph.data && (
              <DamageFlow
                graph={graph.data}
                grouping={grouping}
                aboveChance={aboveChance}
                selectedId={selected?.id ?? null}
                onSelect={setSelected}
              />
            )}
          </div>
        </Panel>
      )}
      {view === "side_by_side" && (
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
                ) : undefined
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
      )}
      {view === "3d" && (
        <Panel
          title={`Connectome as ${gene} ${perturbLabel} unfolds`}
          aside={
            <span className="flex shrink-0 items-center gap-3 text-[11.5px] whitespace-nowrap text-muted-foreground">
              <Legend swatch="bg-seed" label="seed" />
              <Legend swatch="bg-foreground/70" label="healthy" />
              <Legend swatch="bg-signal" label="above chance" />
            </span>
          }
        >
          <div className="h-[600px]">
            {graph.error && <ErrorNote error={graph.error} />}
            {graph.data && (
              <Network3D
                graph={graph.data}
                aboveChance={aboveChance}
                result={result}
                selectedId={selected?.id ?? null}
                onSelect={setSelected}
              />
            )}
          </div>
        </Panel>
      )}
      {selected ? (
        <NeuronDetail node={selected} result={result} onClose={() => setSelected(null)} />
      ) : (
        <p className="px-1 text-[12.5px] text-muted-foreground">
          {view === "flow"
            ? "Each column is one more synapse from the seeds. Hover a row to trace its path; click it to see the strongest paths into its most hit neuron."
            : view === "3d"
              ? "Orbit the graph. Replay walks from healthy (t=0) to degenerated. Hover a neuron for its label; click it for paths."
              : "Same neurons, same positions. Click a neuron to see the paths that carry the loss to it."}
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
  const genes = useQuery({ queryKey: ["genes", ws.disease], queryFn: () => api.genes(ws.disease!), enabled: !!ws.disease });
  const blocked = genes.data?.find((g) => g.human_gene === ws.gene)?.simulatable === false;

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
          blocked ? (
            <EmptyState title={`${ws.gene} can’t be simulated yet`}>
              “Why these neurons?” on the left says what’s missing. Pick another gene to run.
            </EmptyState>
          ) : (
            <EmptyState title={ws.gene ? `Ready to perturb ${ws.gene}` : "No run yet"}>
              {ws.gene
                ? "Run it here or from the left, or ask the agent a what-if."
                : "Pick a disease and a gene on the left, or ask the agent on the right."}
              <RunCta />
            </EmptyState>
          )
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
