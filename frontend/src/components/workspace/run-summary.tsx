"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, SNAPSHOT_MODE } from "@/lib/api";
import { LEVEL_LABEL } from "@/lib/format";
import type { SimulationRequest, SimulationResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { requestKey, runLabel, useWorkspace } from "@/lib/workspace";
import { useSimulate } from "./perturbation";
import { ErrorNote } from "./primitives";

// Gemini's structured read of one run (POST /runs/{id}/summary). Asked for on
// click, not on every run, to spend the free-tier quota only when wanted.
// The z-scores shown are the run's own; the backend drops any circuit the run
// doesn't contain.
export function RunSummaryCard({ result }: { result: SimulationResult }) {
  const ws = useWorkspace();
  const simulate = useSimulate();
  // Fetched only on click (enabled: false), then cached per run.
  const summary = useQuery({
    queryKey: ["summary", result.run_id],
    queryFn: () => api.runSummary(result.run_id),
    enabled: false,
    staleTime: Infinity,
    retry: false,
  });
  const data = summary.data;

  if (SNAPSHOT_MODE) return null;

  if (!data) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed px-4 py-3">
        <p className="text-[12.5px] text-muted-foreground">
          Gemini can read this run and write a short summary: the circuits that stand out, the caveats, and one experiment to run next.
        </p>
        <Button variant="outline" size="sm" onClick={() => summary.refetch()} disabled={summary.isFetching}>
          {summary.isFetching ? <Loader2 className="animate-spin" /> : <Sparkles className="text-signal" />}
          Summarize this run
        </Button>
        {summary.error && <ErrorNote error={summary.error} />}
      </div>
    );
  }

  const next = data.next_experiment.request;
  const nextReq: SimulationRequest | null = next
    ? { ...next, high_confidence_only: result.request.high_confidence_only }
    : null;
  const nextRun = nextReq && ws.runs.find((r) => r.key === requestKey(nextReq));

  return (
    <div className="rounded-xl border bg-card">
      <div className="flex items-center gap-2 border-b px-4 py-2.5">
        <Sparkles className="size-3.5 text-signal" />
        <h3 className="text-[13px] font-medium">Summary</h3>
        <span className="ml-auto text-[11px] text-faint">written by {data.model}; numbers from the run</span>
      </div>
      <div className="grid gap-4 px-4 py-3.5">
        <p className="text-[14px] leading-snug font-medium">{data.headline}</p>

        {data.top_circuits.length > 0 && (
          <ol className="grid gap-2">
            {data.top_circuits.map((c) => (
              <li key={`${c.level}|${c.group}`} className="grid grid-cols-[1fr_auto] items-baseline gap-x-3 text-[13px]">
                <span>
                  <span className="font-medium">{c.group}</span>
                  <span className="text-[11.5px] text-faint"> · {LEVEL_LABEL[c.level] ?? c.level}</span>
                </span>
                <span className={cn("font-mono tabular", c.above_chance ? "text-signal" : "text-muted-foreground")}>
                  z {c.z_score.toFixed(1)}
                </span>
                <span className="col-span-2 text-[12.5px] leading-snug text-muted-foreground">{c.why}</span>
              </li>
            ))}
          </ol>
        )}

        {data.caveats.length > 0 && (
          <div>
            <div className="mb-1 text-[12px] text-muted-foreground">Caveats</div>
            <ul className="grid gap-1 text-[12.5px] leading-snug">
              {data.caveats.map((c) => (
                <li key={c} className="relative pl-3 before:absolute before:top-[0.55em] before:left-0 before:size-1 before:rounded-full before:bg-foreground/40">
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        {data.next_experiment.description && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
            <div className="min-w-0">
              <div className="text-[12px] text-muted-foreground">Next experiment</div>
              <div className="text-[13px] font-medium">{data.next_experiment.description}</div>
              <div className="text-[12px] leading-snug text-muted-foreground">{data.next_experiment.why}</div>
            </div>
            {nextReq && (
              <Button
                size="sm"
                variant="outline"
                disabled={simulate.isPending}
                onClick={() => (nextRun ? ws.set({ activeKey: nextRun.key, tab: "overview" }) : simulate.mutate(nextReq))}
              >
                {simulate.isPending ? <Loader2 className="animate-spin" /> : <FlaskConical />}
                {nextRun ? "Open" : "Run"} {runLabel(nextReq)}
              </Button>
            )}
          </div>
        )}
        {simulate.error && <ErrorNote error={simulate.error} />}
      </div>
    </div>
  );
}
