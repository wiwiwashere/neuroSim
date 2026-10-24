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
      <StepHeading title="Disease" />
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
    <section id="gene" className="scroll-mt-4">
      <StepHeading title="Gene" aside={<span className="text-[11px] text-faint">fly ortholog · evidence</span>} />
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
                "grid w-full grid-cols-[4.5rem_1fr_auto] items-center gap-2 border-b px-3 py-2.5 text-left last:border-0",
                "transition-colors",
                active ? "bg-secondary font-medium" : "hover:bg-secondary/60",
              )}
            >
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
              <span className="flex items-center gap-1.5">
                {g.simulatable ? (
                  <TierBadge tier={g.best_tier} />
                ) : (
                  <span className="text-[11px] text-faint">{g.why_not === "no_evidence" ? "no evidence yet" : "can’t simulate"}</span>
                )}
                <Check className={cn("size-3.5", active ? "text-foreground" : "invisible")} aria-label={active ? "selected" : undefined} />
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
