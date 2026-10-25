"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, SNAPSHOT_MODE } from "@/lib/api";
import { diseaseName } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { CustomDiseasePanel, useCustomChanged, useCustomDiseases } from "./custom-disease";
import { ErrorNote, FlyGene, StepHeading, TierBadge } from "./primitives";

export function DiseasePicker() {
  const ws = useWorkspace();
  const diseases = useQuery({ queryKey: ["diseases"], queryFn: api.diseases });
  const custom = useCustomDiseases();
  const [adding, setAdding] = useState(false);
  const changed = useCustomChanged();
  const remove = useMutation({
    mutationFn: (id: string) => api.removeCustom(id),
    onSuccess: (_, id) => {
      changed();
      if (ws.disease === id) ws.set({ disease: null, gene: null });
    },
  });
  const { disease, set } = ws;
  const customById = new Map((custom.data ?? []).map((d) => [d.id, d]));

  // With only one disease there is nothing to choose, so open its gene list.
  useEffect(() => {
    if (!disease && diseases.data?.length === 1) set({ disease: diseases.data[0] });
  }, [disease, diseases.data, set]);

  return (
    <section>
      <StepHeading
        title="Disease"
        aside={
          !SNAPSHOT_MODE && !adding ? (
            <button type="button" onClick={() => setAdding(true)} className="inline-flex items-center gap-1 text-[11.5px] text-muted-foreground hover:text-foreground">
              <Plus className="size-3" /> Add your own
            </button>
          ) : undefined
        }
      />
      {diseases.error && <ErrorNote error={diseases.error} />}
      <div className="grid gap-1.5">
        {(diseases.data ?? []).map((d) => {
          const active = ws.disease === d;
          const mine = customById.get(d);
          return (
            <div key={d} className="flex items-stretch gap-1">
              <button
                onClick={() => ws.set({ disease: d, gene: null })}
                className={cn(
                  "flex min-w-0 flex-1 items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2.5 text-left text-sm transition-colors",
                  active ? "border-foreground/40 shadow-[0_0_0_1px_var(--foreground)]/10" : "hover:border-foreground/25",
                  mine && "border-dashed",
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{mine ? mine.name : diseaseName(d)}</span>
                  {mine && (
                    <span className="block truncate text-[11px] text-seed" title={`${mine.n_rows} rows from ${mine.file}, not reviewed by Bio`}>
                      your data · {mine.genes.join(", ")}
                    </span>
                  )}
                </span>
                {active && <Check className="size-4 shrink-0 text-foreground" aria-label="selected" />}
              </button>
              {mine && (
                <Button
                  size="icon-sm"
                  variant="ghost"
                  className="h-auto shrink-0"
                  title={`Remove ${mine.name} and its rows`}
                  aria-label={`Remove ${mine.name}`}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(d)}
                >
                  <Trash2 />
                </Button>
              )}
            </div>
          );
        })}
        {diseases.isPending && <div className="h-11 animate-pulse rounded-lg bg-muted" />}
      </div>
      {remove.error && <ErrorNote error={remove.error} />}
      {adding && (
        <CustomDiseasePanel
          onClose={() => setAdding(false)}
          onSaved={(d) => {
            setAdding(false);
            ws.set({ disease: d.id, gene: null });
          }}
        />
      )}
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
