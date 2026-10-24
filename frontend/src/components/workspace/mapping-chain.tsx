"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { int } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { ConfidenceMeter, ErrorNote, evidenceKey, FlyGene, StepHeading, TierBadge, UploadedQuote, uniqueEvidence } from "./primitives";

/** One link in the chain. The rail on the left joins the cards into a sequence. */
function Link({ kicker, children, confidence, last }: { kicker: string; children: ReactNode; confidence?: number; last?: boolean }) {
  return (
    <li className="relative pl-5">
      <span className="absolute top-[14px] left-[5px] size-[7px] rounded-full border border-foreground/50 bg-card" />
      {!last && <span className="absolute top-[24px] bottom-[-10px] left-[8px] w-px bg-border" />}
      <div className="rounded-lg border bg-card px-3 py-2.5">
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="text-[12px] text-muted-foreground">{kicker}</span>
          {confidence !== undefined && <ConfidenceMeter value={confidence} />}
        </div>
        {children}
      </div>
    </li>
  );
}

export function MappingChain() {
  const ws = useWorkspace();
  const genes = useQuery({ queryKey: ["genes", ws.disease], queryFn: () => api.genes(ws.disease!), enabled: !!ws.disease });
  const option = genes.data?.find((g) => g.human_gene === ws.gene);
  const simulatable = option?.simulatable ?? false;

  const chain = useQuery({
    queryKey: ["chain", ws.gene, ws.highConfidenceOnly],
    queryFn: () => api.chain(ws.gene!, ws.highConfidenceOnly),
    enabled: !!ws.gene && simulatable,
  });

  if (!ws.gene || !option) return null;

  const toggle = (
    <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-muted-foreground">
      High-confidence only
      <Switch
        checked={ws.highConfidenceOnly}
        onCheckedChange={(v) => ws.set({ highConfidenceOnly: v })}
        disabled={!simulatable}
        className="scale-[0.8]"
      />
    </label>
  );

  if (!simulatable) {
    return (
      <section>
        <StepHeading title="Why these neurons?" />
        <div className="rounded-lg border border-dashed bg-card px-3.5 py-3 text-[13px]">
          <p className="font-medium">
            <span className="font-mono">{ws.gene}</span> has no fly ortholog.
          </p>
          <p className="mt-1 text-muted-foreground">
            With no matching fly gene there is no published fly model to say which neurons are lost, so neuroSim
            doesn’t simulate it rather than guess.
          </p>
        </div>
      </section>
    );
  }

  const c = chain.data;
  const evidence = c ? uniqueEvidence(c) : [];
  const clusters = c ? [...new Set(c.seed_types.map((t) => t.cluster))] : [];
  const nNeurons = c ? c.seed_types.reduce((n, t) => n + t.n_neurons, 0) : 0;

  return (
    <section id="chain" className="scroll-mt-4">
      <StepHeading title="Why these neurons?" aside={toggle} />
      {chain.error && <ErrorNote error={chain.error} />}
      {chain.isPending && <div className="h-64 animate-pulse rounded-lg bg-muted/60" />}
      {c && (
        <ol className="grid gap-2.5">
          <Link kicker="Human gene">
            <p className="font-mono text-[15px] font-medium">{c.human_gene}</p>
          </Link>

          <Link kicker="Fly ortholog · DIOPT" confidence={c.ortholog.confidence}>
            <p className="text-[15px]">
              {c.ortholog.fly_genes.map((f, i) => (
                <span key={f}>
                  {i > 0 && ", "}
                  <FlyGene>{f}</FlyGene>
                </span>
              ))}
            </p>
            <p className="mt-0.5 text-[12px] text-muted-foreground">
              DIOPT score {c.ortholog.diopt_score ?? "—"} · {c.ortholog.relationship}
            </p>
          </Link>

          <Link kicker="Dopamine clusters lost">
            <p className="font-mono text-[14px]">{clusters.join(", ")}</p>
            <ul className="mt-1.5 grid gap-2">
              {evidence.map((e) => (
                <li key={evidenceKey(e)} className="border-t pt-1.5 text-[12px] leading-snug">
                  <p className="text-foreground/90">{e.finding}</p>
                  <UploadedQuote row={e} />
                  <div className="mt-1 flex items-center justify-between gap-2 text-muted-foreground">
                    <a href={e.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                      {e.citation}
                      <ExternalLink className="size-3" />
                    </a>
                    <span className="flex items-center gap-1.5">
                      <span className="text-[11px]">{e.model_type}</span>
                      <TierBadge tier={e.tier} />
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </Link>

          <Link kicker="Connectome cell types">
            <ul className="grid gap-1">
              {c.seed_types.map((t) => (
                <li key={t.cell_type} className="grid grid-cols-[1fr_auto_auto] items-center gap-2.5 text-[12.5px]">
                  <span className="font-mono">{t.cell_type}</span>
                  <span
                    className={cn(
                      "rounded px-1 text-[10.5px]",
                      t.match === "exact" ? "bg-secondary text-foreground" : "border border-dashed text-muted-foreground",
                    )}
                  >
                    {t.match}
                  </span>
                  <ConfidenceMeter value={t.confidence} />
                </li>
              ))}
            </ul>
          </Link>

          <Link kicker="Seed neurons" last>
            <p className="flex items-baseline gap-1.5">
              <span className="font-mono text-[22px] leading-none tabular">{int(nNeurons)}</span>
              <span className="text-[12.5px] text-muted-foreground">
                neurons across {c.seed_types.length} cell type{c.seed_types.length === 1 ? "" : "s"}
              </span>
            </p>
          </Link>
        </ol>
      )}
    </section>
  );
}
