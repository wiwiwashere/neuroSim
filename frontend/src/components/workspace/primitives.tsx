import type { ReactNode } from "react";
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
      {children && <p className="max-w-sm text-[13px] text-muted-foreground">{children}</p>}
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
