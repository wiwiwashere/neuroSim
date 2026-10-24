import type { GroupScore, SankeyLink } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface RegionShare {
  group: string;
  /** This region's part of all the damage, 0..1. */
  share: number;
  /** Seed cluster -> its part of this region's damage, 0..1 of the total. */
  byCluster: { cluster: string; share: number }[];
  score: GroupScore | null;
}

/**
 * Splits the run's total damage by super region. The Sankey links already hold
 * summed impact per (seed cluster, region); when they are missing the group
 * scores stand in (mean impact x neurons is the same sum).
 */
export function regionShares(links: SankeyLink[] | undefined, groups: GroupScore[]): RegionShare[] {
  const byGroup = new Map(groups.map((g) => [g.group, g]));
  const totals = new Map<string, Map<string, number>>();
  if (links?.length) {
    for (const l of links) {
      const t = totals.get(l.target) ?? new Map<string, number>();
      t.set(l.source, (t.get(l.source) ?? 0) + l.value);
      totals.set(l.target, t);
    }
  } else {
    for (const g of groups) totals.set(g.group, new Map([["", Math.max(0, g.mean_impact * g.n_neurons)]]));
  }
  const sum = (m: Map<string, number>) => [...m.values()].reduce((s, v) => s + v, 0);
  const grand = [...totals.values()].reduce((s, m) => s + sum(m), 0);
  if (grand <= 0) return [];
  return [...totals.entries()]
    .map(([group, m]) => ({
      group,
      share: sum(m) / grand,
      byCluster: [...m.entries()]
        .map(([cluster, v]) => ({ cluster, share: v / grand }))
        .sort((x, y) => x.cluster.localeCompare(y.cluster)),
      score: byGroup.get(group) ?? null,
    }))
    .sort((a, b) => b.share - a.share);
}

const sharePct = (x: number) => (x < 0.01 ? "<1%" : `${Math.round(x * 100)}%`);

/**
 * Where the damage goes, as one labelled bar per region: length is the
 * region's share of all the damage, blue when the region is hit harder than
 * random dopamine neurons would hit it.
 */
export function DamageBars({ shares }: { shares: RegionShare[] }) {
  const max = Math.max(...shares.map((s) => s.share), 1e-9);
  const clusters = [...new Set(shares.flatMap((s) => s.byCluster.map((c) => c.cluster)))].filter(Boolean);
  return (
    <ol className="grid gap-3">
      {shares.map((s) => {
        const above = s.score?.above_chance ?? false;
        return (
          <li key={s.group} className="grid grid-cols-[minmax(8rem,13rem)_1fr_auto] items-center gap-x-4 gap-y-1">
            <div className="min-w-0">
              <div className="truncate text-[13.5px] font-medium">{s.group}</div>
              {s.score?.function_label && <div className="truncate text-[12px] text-muted-foreground">{s.score.function_label}</div>}
            </div>
            <div className="flex items-center gap-2.5">
              <div className="relative h-5 flex-1 overflow-hidden rounded-[4px] bg-muted/70">
                {/* One segment per seed cluster when there are several, so the split is visible too. */}
                <div className="absolute inset-y-0 left-0 flex" style={{ width: `${(s.share / max) * 100}%` }}>
                  {s.byCluster.map((c, i) => (
                    <div
                      key={c.cluster || i}
                      title={c.cluster ? `${c.cluster}: ${sharePct(c.share)} of all damage` : undefined}
                      className={cn("h-full", above ? "bg-signal" : "bg-faint/70", i > 0 && "border-l-2 border-card")}
                      style={{ width: `${(c.share / s.share) * 100}%`, opacity: clusters.length > 1 ? 1 - i * 0.22 : 1 }}
                    />
                  ))}
                </div>
              </div>
              <span className="w-10 text-right font-mono text-[13px] font-medium tabular">{sharePct(s.share)}</span>
            </div>
            <span className={cn("text-[12px] whitespace-nowrap", above ? "font-medium text-signal" : "text-muted-foreground")}>
              {s.score ? (above ? `above chance · z ${s.score.z_score.toFixed(1)}` : `within chance · z ${s.score.z_score.toFixed(1)}`) : ""}
            </span>
          </li>
        );
      })}
      {clusters.length > 1 && (
        <li className="text-[11.5px] text-muted-foreground">Segments, left to right: {clusters.join(", ")}. Hover one for its share.</li>
      )}
    </ol>
  );
}
