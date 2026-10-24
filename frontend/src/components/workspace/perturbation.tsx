"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api } from "@/lib/api";
import type { PerturbationMode, SimulationRequest } from "@/lib/types";
import { requestKey, useWorkspace } from "@/lib/workspace";
import { ErrorNote, StepHeading } from "./primitives";

export function useSimulate(source: "you" | "agent" = "you") {
  const ws = useWorkspace();
  return useMutation({
    mutationFn: (req: SimulationRequest) => api.simulate(req),
    onSuccess: (result) => ws.addRun(result, source),
  });
}

export function Perturbation() {
  const ws = useWorkspace();
  const genes = useQuery({ queryKey: ["genes", ws.disease], queryFn: () => api.genes(ws.disease!), enabled: !!ws.disease });
  const simulate = useSimulate();
  const option = genes.data?.find((g) => g.human_gene === ws.gene);
  if (!ws.gene || !option?.simulatable) return null;

  const req: SimulationRequest = {
    human_gene: ws.gene,
    mode: ws.mode,
    strength: ws.mode === "knockout" ? 1 : ws.strength,
    high_confidence_only: ws.highConfidenceOnly,
  };
  const already = ws.activeKey === requestKey(req);

  return (
    <section>
      <StepHeading title="Perturbation" />
      <div className="grid gap-3.5 rounded-lg border bg-card p-3">
        <ToggleGroup
          type="single"
          value={ws.mode}
          onValueChange={(v) => v && ws.set({ mode: v as PerturbationMode })}
          variant="outline"
          className="w-full"
        >
          <ToggleGroupItem value="knockout" className="flex-1 text-[12.5px]">
            Knockout
          </ToggleGroupItem>
          <ToggleGroupItem value="reduce_output" className="flex-1 text-[12.5px]">
            Reduce output
          </ToggleGroupItem>
        </ToggleGroup>

        <div className={ws.mode === "knockout" ? "pointer-events-none opacity-40" : undefined} aria-disabled={ws.mode === "knockout"}>
          <div className="mb-2 flex items-baseline justify-between text-[12.5px]">
            <span className="text-muted-foreground">Output lost</span>
            <span className="font-mono tabular">{ws.mode === "knockout" ? "100" : Math.round(ws.strength * 100)}%</span>
          </div>
          <Slider
            min={0.05}
            max={1}
            step={0.05}
            value={[ws.mode === "knockout" ? 1 : ws.strength]}
            onValueChange={([v]) => ws.set({ strength: v })}
            aria-label="Share of seed output lost"
          />
          <p className="mt-2 text-[11.5px] leading-snug text-faint">
            Results scale linearly with strength; rankings don’t change.
          </p>
        </div>

        <Button onClick={() => simulate.mutate(req)} disabled={simulate.isPending} className="w-full">
          {simulate.isPending ? <Loader2 className="animate-spin" /> : <Play className="fill-current" />}
          {already ? "Run again" : "Run simulation"}
        </Button>
        {simulate.error && <ErrorNote error={simulate.error} />}
      </div>
    </section>
  );
}
