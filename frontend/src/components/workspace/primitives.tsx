import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import type { EvidenceRow, GeneExpression, SeedSet } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Section heading used down the left column. */
export function StepHeading({ title, aside }: { title: string; aside?: ReactNode }) {
  return (
    <div className="mb-2.5 flex items-baseline justify-between gap-2">
      <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
      {aside}
    </div>
  );
}

/** A 0..1 confidence as a thin meter plus the number, so it never relies on length alone. */
export function ConfidenceMeter({ value, className }: { value: number; className?: string }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)} title={`Confidence ${v.toFixed(2)}`}>
      <span className="relative h-1 w-10 overflow-hidden rounded-full bg-muted">
        <span className="absolute inset-y-0 left-0 rounded-full bg-foreground/70" style={{ width: `${v * 100}%` }} />
      </span>
      <span className="font-mono text-[11px] text-muted-foreground tabular">{v.toFixed(2)}</span>
    </span>
  );
}

const TIER_STYLE: Record<string, string> = {
  high: "border-foreground/30 text-foreground",
  medium: "border-foreground/20 text-muted-foreground",
  low: "border-dashed border-foreground/25 text-muted-foreground",
};

/** Evidence tier. Encoded by border weight/style and the word, not by colour. */
export function TierBadge({ tier }: { tier: string | null | undefined }) {
  if (!tier) return null;
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded border px-1.5 text-[10.5px] font-medium uppercase tracking-wide",
        TIER_STYLE[tier] ?? TIER_STYLE.low,
      )}
    >
      {tier}
    </span>
  );
}

/** A tile with one headline number. */
export function StatTile({
  label,
  value,
  sub,
  emphasis,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  emphasis?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-[12px] text-muted-foreground">{label}</span>
      <span
        className={cn(
          "tabular leading-none tracking-[-0.02em]",
          emphasis ? "text-[44px] font-semibold" : "text-[26px] font-medium",
        )}
      >
        {value}
      </span>
      {sub && <span className="text-[12px] text-muted-foreground">{sub}</span>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-1.5 px-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="flex max-w-sm flex-col items-center text-[13px] text-muted-foreground">{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  return (
    <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[12.5px] text-destructive">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}

/** Fly gene symbols are italic by convention. */
export function FlyGene({ children }: { children: ReactNode }) {
  return <i className="font-mono italic">{children}</i>;
}

/** Each evidence row behind a seed set once, in table order. */
export function uniqueEvidence(seeds: SeedSet): EvidenceRow[] {
  const seen = new Map<string, EvidenceRow>();
  for (const t of seeds.seed_types) for (const e of t.evidence) seen.set(evidenceKey(e), e);
  return [...seen.values()];
}

export const evidenceKey = (e: EvidenceRow) => e.extracted?.id ?? e.user_supplied?.id ?? `${e.citation}|${e.clusters.join()}`;

/** The one label every view carries for data the person added themselves. */
export const USER_SUPPLIED_LABEL = "user-supplied · not reviewed by Bio";

export function UserSuppliedBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-4 items-center rounded border border-dashed border-seed/70 px-1 text-[10px] font-medium uppercase not-italic tracking-wide text-seed",
        className,
      )}
      title="Added by a user of this app from their own table. Nobody on the team has checked it."
    >
      {USER_SUPPLIED_LABEL}
    </span>
  );
}

/** Marks a row from a user-added disease, with where it came from. */
export function UserSuppliedNote({ row }: { row: EvidenceRow }) {
  const u = row.user_supplied;
  if (!u) return null;
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[11.5px] leading-snug text-muted-foreground">
      <UserSuppliedBadge />
      <span>from {u.file}</span>
      {u.non_dopamine && u.non_dopamine.length > 0 && (
        <span className="text-faint">· {u.non_dopamine.join(", ")} not dopamine; the baseline still draws dopamine neurons</span>
      )}
    </p>
  );
}

/** Marks a row Bio approved from a paper upload, with the quote it rests on. */
export function UploadedQuote({ row }: { row: EvidenceRow }) {
  const x = row.extracted;
  if (!x) return null;
  return (
    <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">
      <span className="mr-1 inline-flex h-4 items-center rounded border border-dashed border-foreground/30 px-1 text-[10px] font-medium uppercase not-italic tracking-wide text-foreground/80">
        uploaded paper
      </span>
      <span className="italic">“{x.quote}”</span>
      <span className="text-faint">
        {x.page ? ` p. ${x.page}` : ""}
        {x.quote_found === false ? " · quote not found word for word" : ""}
        {x.edited?.length ? ` · edited by Bio: ${x.edited.join(", ")}` : ""}
      </span>
    </p>
  );
}

/** TPM as the atlas gives it; bulk RNA-seq can't tell values under 1 from nothing. */
export const tpm = (v: number) => (v < 1 ? "<1" : String(Math.round(v)));

/**
 * Kait's expression atlas for a gene's fly orthologs (Davis et al. 2020, PAM only).
 * Context for the chain, never a filter: clusters the atlas didn't profile are
 * "not measured", and nothing here changes a seed or its confidence.
 */
export function ExpressionNote({ expression: x, seedClusters }: { expression: GeneExpression; seedClusters?: string[] }) {
  const measured = new Set(x.clusters_measured);
  // ALL_DA pools every dopamine neuron, so the atlas covers part of it (the PAM ones).
  const allDa = (seedClusters ?? []).includes("ALL_DA");
  const unmeasured = (seedClusters ?? []).filter((c) => !measured.has(c) && c !== "ALL_DA");
  const ranges = x.fly_genes.map((f) => {
    const values = x.cell_types.map((c) => c.tpm[f]).filter((v): v is number => v !== undefined);
    return { gene: f, lo: Math.min(...values), hi: Math.max(...values) };
  });
  return (
    <div className="grid gap-1 text-[12px] leading-snug">
      <p>
        {ranges.map((r, i) => (
          <span key={r.gene}>
            {i > 0 && ", "}
            <FlyGene>{r.gene}</FlyGene>{" "}
            <span className="font-mono tabular">
              {r.lo === r.hi ? tpm(r.lo) : `${tpm(r.lo)}–${tpm(r.hi)}`}
            </span>{" "}
            TPM
          </span>
        ))}{" "}
        <span className="text-muted-foreground">
          across {x.cell_types.length} {x.clusters_measured.join(", ")} cell types
        </span>
      </p>
      {allDa && (
        <p className="text-muted-foreground">
          These seeds are every dopamine neuron; the atlas only profiled the {x.clusters_measured.join(", ")} ones.
        </p>
      )}
      {unmeasured.length > 0 && (
        <p className="text-muted-foreground">
          The atlas didn’t profile {unmeasured.join(", ")}, so {unmeasured.length > 1 ? "those seeds are" : "that seed is"} not
          measured here, which is not the same as not expressed.
        </p>
      )}
      {x.missing_fly_genes.length > 0 && (
        <p className="text-muted-foreground">
          {x.missing_fly_genes.map((f, i) => (
            <span key={f}>
              {i > 0 && ", "}
              <FlyGene>{f}</FlyGene>
            </span>
          ))}{" "}
          isn’t in the atlas.
        </p>
      )}
      <details className="text-muted-foreground">
        <summary className="cursor-pointer text-[11.5px] select-none hover:text-foreground">Values per cell type</summary>
        <ul className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11.5px]">
          {x.cell_types.map((c) => (
            <li key={c.cell_type} className="contents">
              <span className="font-mono">
                {c.cell_type}
                {c.match === "coarse" && <span className="text-faint" title={`From a driver line that pools several PAM types: ${c.atlas_labels.join(", ")}`}> *</span>}
              </span>
              <span className="font-mono tabular">{x.fly_genes.map((f) => `${f} ${c.tpm[f] === undefined ? "—" : tpm(c.tpm[f])}`).join(" · ")}</span>
            </li>
          ))}
        </ul>
        {x.cell_types.some((c) => c.match === "coarse") && (
          <p className="mt-1 text-[11px] text-faint">* from a driver line that pools several PAM types</p>
        )}
      </details>
      <p className="text-[11px] text-faint">
        <a href={x.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
          {x.citation}
          <ExternalLink className="size-3" />
        </a>{" "}
        · bulk RNA-seq · context only, it never removes a seed or changes its confidence
      </p>
    </div>
  );
}
