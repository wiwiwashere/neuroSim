"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, Loader2 } from "lucide-react";
import dynamic from "next/dynamic";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { LEVEL_LABEL } from "@/lib/format";
import type { GroupLevel, SimulationResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { type RunEntry, useWorkspace } from "@/lib/workspace";
import { EmptyState, ErrorNote, StatTile } from "./primitives";

const RankedBars = dynamic(() => import("@/components/charts/ranked-bars").then((m) => m.RankedBars), { ssr: false });

function levelFor(a: SimulationResult, b: SimulationResult, wanted: GroupLevel): GroupLevel {
  if (a.groups[wanted]?.length && b.groups[wanted]?.length) return wanted;
  return "super_region";
}

export function CompareTab() {
  const ws = useWorkspace();
  const a = ws.activeRun;
  const b = ws.compareRun;
  const disease = a?.result.seeds.disease ?? ws.disease;
  const genes = useQuery({ queryKey: ["genes", disease], queryFn: () => api.genes(disease!), enabled: !!disease });
  const [geneB, setGeneB] = useState<string>("");

  const runB = useMutation({
    mutationFn: (gene: string) =>
      api.simulate({ human_gene: gene, mode: a!.result.request.mode, strength: a!.result.request.strength, high_confidence_only: a!.result.request.high_confidence_only }),
    onSuccess: (result) => {
      const entry = ws.addRun(result, "you", { activate: false });
      ws.set({ compareKey: entry.key });
    },
  });

  if (!a) return <EmptyState title="Run one gene first">Compare puts a second gene’s ranking beside the run you’re looking at.</EmptyState>;

  const options = (genes.data ?? []).filter((g) => g.simulatable && g.human_gene !== a.result.request.human_gene);
  const others = ws.runs.filter((r) => r.key !== a.key);
  const pick = geneB || options[0]?.human_gene || "";

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-card px-4 py-3 text-[13px]">
        <span className="font-mono font-medium">{a.label}</span>
        <ArrowLeftRight className="size-4 text-faint" />
        {others.length > 0 && (
          <select
            value={b && b.key !== a.key ? b.key : ""}
            onChange={(e) => ws.set({ compareKey: e.target.value || null })}
            className="h-8 rounded-md border bg-card px-2 font-mono text-[12.5px]"
          >
            <option value="">pick a run…</option>
            {others.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
        )}
        <span className="text-muted-foreground">{others.length > 0 ? "or run" : "Run"}</span>
        <select value={pick} onChange={(e) => setGeneB(e.target.value)} className="h-8 rounded-md border bg-card px-2 font-mono text-[12.5px]">
          {options.map((g) => (
            <option key={g.human_gene} value={g.human_gene}>
              {g.human_gene}
            </option>
          ))}
        </select>
        <Button size="sm" variant="outline" disabled={!pick || runB.isPending} onClick={() => runB.mutate(pick)}>
          {runB.isPending && <Loader2 className="animate-spin" />}
          Run and compare
        </Button>
        {runB.error && <ErrorNote error={runB.error} />}
      </div>

      {b && b.key !== a.key ? <ComparePair a={a} b={b} /> : (
        <EmptyState title="Pick a second gene">Do two genes hit the same circuits? The demo pair is PINK1 and PRKN.</EmptyState>
      )}
    </div>
  );
}

function ComparePair({ a, b }: { a: RunEntry; b: RunEntry }) {
  const ws = useWorkspace();
  const level = levelFor(a.result, b.result, ws.level);
  const cmp = useQuery({
    queryKey: ["compare", a.result.run_id, b.result.run_id, level],
    queryFn: () => api.compare(a.result.run_id, b.result.run_id, level),
  });
  const shared = new Set(cmp.data?.shared_top ?? []);

  return (
    <>
      {cmp.error && <ErrorNote error={cmp.error} />}
      {cmp.data && (
        <div className="grid grid-cols-[auto_1fr] items-center gap-8 rounded-xl border bg-card px-5 py-4">
          <StatTile emphasis label="Rank correlation (Spearman ρ)" value={cmp.data.spearman_rho.toFixed(2)} sub={`${LEVEL_LABEL[level]} level`} />
          <div className="grid gap-2.5">
            <p className="text-[14px] leading-snug">{cmp.data.summary}</p>
            <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-[12px]">
              <Chips label="In both top lists" items={cmp.data.shared_top} strong />
              <Chips label={`Only ${a.result.request.human_gene}`} items={cmp.data.only_a} />
              <Chips label={`Only ${b.result.request.human_gene}`} items={cmp.data.only_b} />
            </div>
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-4">
        {[a, b].map((r) => {
          const groups = r.result.groups[level] ?? [];
          return (
            <div key={r.key} className="rounded-xl border bg-card">
              <div className="border-b px-4 py-2.5 font-mono text-[13px] font-medium">{r.label}</div>
              <div className="px-1 pt-1" style={{ height: Math.max(220, groups.length * 54 + 80) }}>
                <RankedBars groups={groups} highlight={shared} />
              </div>
            </div>
          );
        })}
      </div>
      <p className="px-1 text-[12px] text-muted-foreground">Bold names are in both genes’ top lists.</p>
    </>
  );
}

function Chips({ label, items, strong }: { label: string; items: string[]; strong?: boolean }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <span className="text-muted-foreground">{label}:</span>
      {items.length === 0 && <span className="text-faint">none</span>}
      {items.map((i) => (
        <span key={i} className={cn("rounded border px-1.5 py-0.5", strong ? "border-signal/50 bg-signal-soft font-medium" : "border-border")}>
          {i}
        </span>
      ))}
    </span>
  );
}
