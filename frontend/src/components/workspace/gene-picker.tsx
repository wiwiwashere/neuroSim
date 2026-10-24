"use client";

import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { api } from "@/lib/api";
import { diseaseName } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { ErrorNote, FlyGene, StepHeading, TierBadge } from "./primitives";

export function DiseasePicker() {
  const ws = useWorkspace();
  const diseases = useQuery({ queryKey: ["diseases"], queryFn: api.diseases });

  return (
    <section>
      <StepHeading n={1} title="Disease" />
      {diseases.error && <ErrorNote error={diseases.error} />}
      <div className="grid gap-1.5">
        {(diseases.data ?? []).map((d) => {
          const active = ws.disease === d;
          return (
            <button
              key={d}
              onClick={() => ws.set({ disease: d, gene: null })}
              className={cn(
                "flex items-center justify-between rounded-lg border bg-card px-3 py-2.5 text-left text-sm transition-colors",
                active ? "border-foreground/40 shadow-[0_0_0_1px_var(--foreground)]/10" : "hover:border-foreground/25",
              )}
            >
              <span className="font-medium">{diseaseName(d)}</span>
              {active && <Check className="size-4 text-foreground" aria-label="selected" />}
            </button>
          );
        })}
        {diseases.isPending && <div className="h-11 animate-pulse rounded-lg bg-muted" />}
      </div>
    </section>
  );
}

export function GenePicker() {
  const ws = useWorkspace();
  const genes = useQuery({
    queryKey: ["genes", ws.disease],
    queryFn: () => api.genes(ws.disease!),
    enabled: !!ws.disease,
  });

  if (!ws.disease) return null;

  return (
    <section>
      <StepHeading n={2} title="Gene" aside={<span className="text-[11px] text-faint">fly ortholog · evidence</span>} />
      {genes.error && <ErrorNote error={genes.error} />}
      <div className="overflow-hidden rounded-lg border bg-card">
        {genes.isPending &&
          Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-11 animate-pulse border-b bg-muted/40 last:border-0" />)}
        {genes.data?.map((g) => {
          const active = ws.gene === g.human_gene;
          return (
            <button
              key={g.human_gene}
              onClick={() => ws.set({ gene: g.human_gene })}
              className={cn(
                "relative grid w-full grid-cols-[4.5rem_1fr_auto] items-center gap-2 border-b px-3 py-2.5 text-left last:border-0",
                "transition-colors",
                active ? "bg-secondary" : "hover:bg-secondary/60",
              )}
            >
              {active && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-r bg-foreground" />}
              <span className={cn("font-mono text-[13px] font-medium", !g.simulatable && "text-faint")}>{g.human_gene}</span>
              <span className="truncate text-[12.5px] text-muted-foreground">
                {g.fly_genes.length ? (
                  g.fly_genes.map((f, i) => (
                    <span key={f}>
                      {i > 0 && ", "}
                      <FlyGene>{f}</FlyGene>
                    </span>
                  ))
                ) : (
                  <span className="text-faint">no fly ortholog</span>
                )}
              </span>
              {g.simulatable ? <TierBadge tier={g.best_tier} /> : <span className="text-[11px] text-faint">can’t simulate</span>}
            </button>
          );
        })}
      </div>
    </section>
  );
}
