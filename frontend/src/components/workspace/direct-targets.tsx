"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, flybaseTermUrl } from "@/lib/api";
import { int } from "@/lib/format";
import type { DirectTarget } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace";
import { ErrorNote, FlyGene, StepHeading, tpm } from "./primitives";

const MATCH_NOTE: Record<string, string> = {
  coarse: "from an atlas line that pools several cell types",
  inferred: "from a promoter fusion that labels every neuron of this kind",
};

/** Atlas values for one target, with the label they come from. Context only. */
function TargetExpressionLine({ target }: { target: DirectTarget }) {
  const x = target.expression;
  if (!x) return null;
  const note = [MATCH_NOTE[x.match], x.note].filter(Boolean).join(". ");
  return (
    <p className="text-[11px] leading-snug text-muted-foreground" title={note || undefined}>
      {Object.entries(x.tpm).map(([gene, v], i) => (
        <span key={gene}>
          {i > 0 && " · "}
          <FlyGene>{gene}</FlyGene> <span className="font-mono tabular">{tpm(v)}</span> TPM
        </span>
      ))}
      {x.match !== "exact" && <span className="text-faint"> *</span>}
      {(x.fbbt_ids ?? []).map((id) => (
        <a
          key={id}
          href={flybaseTermUrl(id)}
          target="_blank"
          rel="noreferrer"
          className="ml-1.5 inline-flex items-center gap-0.5 text-faint underline-offset-2 hover:text-foreground hover:underline"
          title={`Atlas line “${x.atlas_label}” on FlyBase (${id})`}
        >
          FlyBase
          <ExternalLink className="size-2.5" />
        </a>
      ))}
    </p>
  );
}

/**
 * The cell types the gene's lost clusters synapse onto directly, from Kait's
 * one-hop table of FlyWire connections. Real connectivity, not the simulation,
 * so it shows real numbers even while runs serve sample data.
 */
export function DirectTargets() {
  const ws = useWorkspace();
  const genes = useQuery({ queryKey: ["genes", ws.disease], queryFn: () => api.genes(ws.disease!), enabled: !!ws.disease });
  const simulatable = genes.data?.find((g) => g.human_gene === ws.gene)?.simulatable ?? false;
  const targets = useQuery({
    queryKey: ["targets", ws.gene, ws.highConfidenceOnly],
    queryFn: () => api.targets(ws.gene!, ws.highConfidenceOnly),
    enabled: !!ws.gene && simulatable,
  });

  if (!ws.gene || !simulatable) return null;
  const t = targets.data;
  const max = t?.targets[0]?.synapses ?? 1;
  const multi = (t?.clusters.length ?? 0) > 1;

  return (
    <section>
      <StepHeading title="Where their output goes" />
      {targets.error && <ErrorNote error={targets.error} />}
      {targets.isPending && <div className="h-48 animate-pulse rounded-lg bg-muted/60" />}
      {t && (
        <div className="grid gap-2 rounded-lg border bg-card px-3 py-2.5 text-[12.5px]">
          <p className="leading-snug">
            <span className="font-mono">{t.clusters.join(", ")}</span> synapse onto{" "}
            <span className="font-mono tabular">{int(t.n_target_types)}</span> cell types directly,{" "}
            <span className="font-mono tabular">{int(t.total_synapses)}</span> synapses in all. Top {t.targets.length}:
          </p>
          <ul className="grid gap-1.5">
            {t.targets.map((target) => (
              <li key={target.cell_type} className="grid gap-0.5">
                <div className="grid grid-cols-[minmax(0,1fr)_72px_auto] items-center gap-2">
                  <span className="truncate font-mono" title={`${int(target.n_neurons)} neurons of this type get dopamine input`}>
                    {target.cell_type}
                  </span>
                  <span
                    className="h-1.5 overflow-hidden rounded-full bg-muted"
                    title={
                      multi
                        ? Object.entries(target.by_cluster)
                            .map(([c, n]) => `${c} ${int(n)}`)
                            .join(" · ")
                        : undefined
                    }
                  >
                    <span className="block h-full rounded-full bg-foreground/60" style={{ width: `${(target.synapses / max) * 100}%` }} />
                  </span>
                  <span className="font-mono text-[11.5px] text-muted-foreground tabular">{int(target.synapses)}</span>
                </div>
                <TargetExpressionLine target={target} />
              </li>
            ))}
          </ul>
          <div className="grid gap-1 border-t pt-2 text-[11px] leading-snug text-faint">
            {t.clusters_not_covered.length > 0 && (
              <p>{t.clusters_not_covered.join(", ")} isn’t in the table, so its targets aren’t counted here.</p>
            )}
            <p>
              The expression atlas measured {t.n_types_with_expression} of the {int(t.n_target_types)} target types; for the
              rest it is not measured, which is not the same as not expressed.
              {t.targets.some((x) => x.expression && x.expression.match !== "exact") && " * from a pooled or broad atlas line."}
            </p>
            <p>
              {t.citation} · synapse counts, not a simulation
              {t.expression_citation && (
                <>
                  {" · expression "}
                  <a
                    href={t.expression_url ?? undefined}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 underline-offset-2 hover:underline"
                  >
                    {t.expression_citation}
                    <ExternalLink className="size-3" />
                  </a>
                </>
              )}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
