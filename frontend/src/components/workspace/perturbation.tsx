"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api } from "@/lib/api";
import type { PerturbationMode, SimulationRequest } from "@/lib/types";
import { requestKey, runLabel, useWorkspace } from "@/lib/workspace";
import { useCustomDiseaseId } from "./custom-disease";
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
  const customId = useCustomDiseaseId();
  const option = genes.data?.find((g) => g.human_gene === ws.gene);
  if (!ws.gene || !option?.simulatable) return null;

  const req: SimulationRequest = {
    human_gene: ws.gene,
    mode: ws.mode,
    strength: ws.mode === "knockout" ? 1 : ws.strength,
    high_confidence_only: ws.highConfidenceOnly,
    ...(customId ? { disease: customId } : {}),
  };
  const already = ws.activeKey === requestKey(req);

  return (
    // Pinned to the bottom of the left column so Run never scrolls away while the chain expands.
    <section id="perturbation" className="lg:sticky lg:-bottom-5 lg:z-10 lg:-mx-4 lg:border-t lg:bg-background lg:px-4 lg:pt-3 lg:pb-5">
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

        {ws.mode === "reduce_output" && (
        <div>
          <div className="mb-2 flex items-baseline justify-between text-[12.5px]">
            <span className="text-muted-foreground">Output lost</span>
            <span className="font-medium tabular">{Math.round(ws.strength * 100)}%</span>
          </div>
          <Slider
            min={0.05}
            max={1}
            step={0.05}
            value={[ws.strength]}
            onValueChange={([v]) => ws.set({ strength: v })}
            aria-label="Share of seed output lost"
          />
          <p className="mt-2 text-[12px] leading-snug text-muted-foreground">
            Results scale linearly with strength; rankings don’t change.
          </p>
        </div>
        )}

        <Button onClick={() => simulate.mutate(req)} disabled={simulate.isPending} className="w-full">
          {simulate.isPending ? <Loader2 className="animate-spin" /> : <Play className="fill-current" />}
          {already ? "Run again" : "Run simulation"}
        </Button>
        {simulate.error && <ErrorNote error={simulate.error} />}
      </div>
    </section>
  );
}

/** The same Run, offered in the empty results area so the first click is where the eye already is. */
export function RunCta() {
  const ws = useWorkspace();
  const genes = useQuery({ queryKey: ["genes", ws.disease], queryFn: () => api.genes(ws.disease!), enabled: !!ws.disease });
  const simulate = useSimulate();
  const customId = useCustomDiseaseId();
  const option = genes.data?.find((g) => g.human_gene === ws.gene);
  if (!ws.gene || !option?.simulatable) return null;
  const req: SimulationRequest = {
    human_gene: ws.gene,
    mode: ws.mode,
    strength: ws.mode === "knockout" ? 1 : ws.strength,
    high_confidence_only: ws.highConfidenceOnly,
    ...(customId ? { disease: customId } : {}),
  };
  return (
    <Button size="lg" onClick={() => simulate.mutate(req)} disabled={simulate.isPending} className="mt-4">
      {simulate.isPending ? <Loader2 className="animate-spin" /> : <Play className="fill-current" />}
      Run {runLabel(req)}
    </Button>
  );
}
