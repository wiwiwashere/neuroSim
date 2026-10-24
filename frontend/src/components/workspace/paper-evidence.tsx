"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, FileUp, Loader2, Pencil, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, SNAPSHOT_MODE } from "@/lib/api";
import type { EvidenceEdits, EvidenceExtraction, EvidenceProposal, EvidenceRow, EvidenceTier, PaperInput } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ConfidenceMeter, ErrorNote, FlyGene, StepHeading, TierBadge } from "./primitives";

// Paper upload (POST /evidence/extract): a PDF, pasted text or a DOI goes in,
// the model proposes evidence rows with the quote behind each one, and the
// backend checks each row against the evidence table. Bio corrects, approves
// or rejects each row; approved rows seed the next run of that gene and can be
// taken out again. Nothing proposed is used until it is approved.

type Mode = "pdf" | "text" | "doi";
const MODES: { id: Mode; label: string }[] = [
  { id: "pdf", label: "PDF" },
  { id: "text", label: "Paste text" },
  { id: "doi", label: "DOI" },
];

/** After a decision, everything that reads the evidence table is stale. */
function useEvidenceChanged() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["evidence-proposals", "evidence-approved", "genes", "chain"]) qc.invalidateQueries({ queryKey: [key] });
  };
}

export function PaperEvidence() {
  const [mode, setMode] = useState<Mode>("pdf");
  const [text, setText] = useState("");
  const [doi, setDoi] = useState("");
  const [dragging, setDragging] = useState(false);
  const [last, setLast] = useState<EvidenceExtraction | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const pending = useQuery({ queryKey: ["evidence-proposals"], queryFn: api.pendingEvidence, enabled: !SNAPSHOT_MODE });
  const approved = useQuery({ queryKey: ["evidence-approved"], queryFn: api.approvedEvidence, enabled: !SNAPSHOT_MODE });
  const extract = useMutation({
    mutationFn: (paper: PaperInput) => api.extractEvidence(paper),
    onSuccess: (out) => {
      setLast(out);
      qc.invalidateQueries({ queryKey: ["evidence-proposals"] });
    },
  });

  if (SNAPSHOT_MODE) return null;

  const send = (paper: PaperInput) => {
    setLast(null);
    extract.mutate(paper);
  };
  const busy = extract.isPending;
  const rows = pending.data ?? [];

  return (
    <section>
      <StepHeading title="Evidence from a paper" />
      <div className="grid gap-3 rounded-lg border bg-card p-3">
        <p className="text-[12px] leading-snug text-muted-foreground">
          Give a fly paper. The model proposes which neurons it reports lost, with the quote behind each row; nothing is used until
          you approve it.
        </p>

        <div className="grid grid-cols-3 rounded-md border p-0.5 text-[12px]" role="tablist">
          {MODES.map((m) => (
            <button
              key={m.id}
              role="tab"
              aria-selected={mode === m.id}
              onClick={() => setMode(m.id)}
              className={cn("rounded-[5px] py-1", mode === m.id ? "bg-secondary font-medium" : "text-muted-foreground hover:text-foreground")}
            >
              {m.label}
            </button>
          ))}
        </div>

        {mode === "pdf" && (
          <>
            <input
              ref={input}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) send({ file });
                e.target.value = "";
              }}
            />
            <button
              type="button"
              disabled={busy}
              onClick={() => input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const file = e.dataTransfer.files?.[0];
                if (file) send({ file });
              }}
              className={cn(
                "flex flex-col items-center gap-1 rounded-md border border-dashed px-3 py-4 text-[12.5px] text-muted-foreground transition-colors",
                dragging ? "border-foreground/60 bg-secondary" : "hover:border-foreground/40",
                busy && "opacity-60",
              )}
            >
              <FileUp className="size-4" />
              Drop a PDF here or click to choose one
              <span className="text-[11px] text-faint">Text-based PDFs up to 20 MB</span>
            </button>
          </>
        )}
        {mode === "text" && (
          <div className="grid gap-2">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={5}
              placeholder="Paste the abstract, or better, the results and figure legends"
              className="w-full resize-y rounded-md border border-input bg-transparent px-2.5 py-2 text-[12.5px] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
            <Button size="sm" variant="outline" disabled={busy || text.trim().length < 200} onClick={() => send({ text })}>
              Read this text
            </Button>
          </div>
        )}
        {mode === "doi" && (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (doi.trim()) send({ doi: doi.trim() });
            }}
          >
            <Input value={doi} onChange={(e) => setDoi(e.target.value)} placeholder="10.1073/pnas… or a PubMed ID" className="h-8 text-[12.5px]" />
            <Button size="sm" variant="outline" type="submit" disabled={busy || !doi.trim()}>
              Look up
            </Button>
          </form>
        )}

        {busy && (
          <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" /> Reading the paper. This takes up to a few minutes on the free tier.
          </p>
        )}
        {extract.error && <ErrorNote error={extract.error} />}
        {last && !busy && (
          <div className="grid gap-1">
            <p className="text-[12px] text-muted-foreground">
              {last.citation || last.file} · read from the {last.read} ·{" "}
              {last.rows.length
                ? `${last.rows.length} proposed row${last.rows.length > 1 ? "s" : ""}`
                : "no neuron-loss findings in it"}
            </p>
            {[last.note, last.fallback ? `The main model was busy, so ${last.model} read it. Check its rows more closely.` : null]
              .filter(Boolean)
              .map((n) => (
                <p key={n} className="flex gap-1.5 text-[11.5px] leading-snug text-destructive">
                  <AlertTriangle className="mt-px size-3 shrink-0" />
                  {n}
                </p>
              ))}
          </div>
        )}

        {rows.length > 0 && (
          <div className="grid gap-2">
            <p className="text-[11.5px] font-medium text-muted-foreground">Waiting for review ({rows.length})</p>
            {rows.map((row) => (
              <ProposalCard key={row.id} row={row} />
            ))}
          </div>
        )}

        {approved.data && approved.data.length > 0 && <ApprovedList rows={approved.data} />}
      </div>
    </section>
  );
}

function ProposalCard({ row }: { row: EvidenceProposal }) {
  const changed = useEvidenceChanged();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<EvidenceEdits>({});
  const decide = useMutation({
    mutationFn: ({ approve, edits }: { approve: boolean; edits?: EvidenceEdits }) => api.decideEvidence(row.id, approve, edits),
    onSuccess: changed,
  });
  const { checks } = row;
  const quoteNote = [
    row.page ? `p. ${row.page}` : "",
    row.quote_found === true ? "found in the paper" : row.quote_found === false ? "not found word for word" : "",
  ]
    .filter(Boolean)
    .join(" · ");

  if (editing) {
    return (
      <RowEditor
        row={row}
        draft={draft}
        onChange={setDraft}
        busy={decide.isPending}
        error={decide.error}
        onCancel={() => {
          setDraft({});
          setEditing(false);
        }}
        onApprove={() => decide.mutate({ approve: true, edits: draft })}
      />
    );
  }

  return (
    <div className="grid gap-1.5 rounded-md border px-2.5 py-2">
      <div className="flex items-center justify-between gap-2 text-[12.5px]">
        <span>
          <span className="font-medium">{row.human_gene}</span> → <FlyGene>{row.fly_gene}</FlyGene>
          <span className="text-muted-foreground"> · {row.model_type}</span>
        </span>
        <span className="flex items-center gap-2">
          {checks.confidence !== null && <ConfidenceMeter value={checks.confidence} />}
          <TierBadge tier={row.tier} />
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-[12px]">
        <span className="text-muted-foreground">Lost:</span>
        {checks.clusters.length === 0 && <span className="text-muted-foreground">not named</span>}
        {checks.clusters.map((c) => (
          <span
            key={c.name}
            title={
              !c.known
                ? "not in the cluster table"
                : `${c.match} match, ${c.n_cell_types} cell types${c.in_quote ? "" : ", not named in the quote"}`
            }
            className={cn(
              "rounded px-1 font-mono text-[11px]",
              !c.known ? "text-destructive line-through" : c.match === "exact" ? "bg-secondary" : "border border-dashed",
              c.known && !c.in_quote && "text-destructive",
            )}
          >
            {c.name}
          </span>
        ))}
      </div>
      <p className="text-[12.5px] leading-snug">{row.finding}</p>
      <blockquote className="border-l-2 pl-2 text-[12px] leading-snug text-muted-foreground italic">
        “{row.quote}”{" "}
        {quoteNote && <span className="not-italic text-faint">· {quoteNote}</span>}
      </blockquote>
      <p className="text-[11.5px] leading-snug text-faint">
        Tier: {row.tier_reason} · {row.citation || row.source_file}
      </p>
      {checks.problems.length > 0 && (
        <ul className="grid gap-0.5">
          {checks.problems.map((p) => (
            <li key={p} className="flex gap-1.5 text-[11.5px] leading-snug text-destructive">
              <AlertTriangle className="mt-px size-3 shrink-0" />
              {p}
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-1.5 pt-0.5">
        <Button size="sm" variant="outline" className="h-7 flex-1" onClick={() => decide.mutate({ approve: true })} disabled={decide.isPending}>
          <Check /> Approve
        </Button>
        <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditing(true)} disabled={decide.isPending}>
          <Pencil /> Edit
        </Button>
        <Button size="sm" variant="ghost" className="h-7" onClick={() => decide.mutate({ approve: false })} disabled={decide.isPending}>
          <X /> Reject
        </Button>
      </div>
      {decide.error && <ErrorNote error={decide.error} />}
    </div>
  );
}

const TIERS: EvidenceTier[] = ["high", "medium", "low"];

function RowEditor({
  row,
  draft,
  onChange,
  busy,
  error,
  onCancel,
  onApprove,
}: {
  row: EvidenceProposal;
  draft: EvidenceEdits;
  onChange: (d: EvidenceEdits) => void;
  busy: boolean;
  error: unknown;
  onCancel: () => void;
  onApprove: () => void;
}) {
  const value = { ...row, ...draft };
  const set = (patch: EvidenceEdits) => onChange({ ...draft, ...patch });
  const field = "h-7 text-[12px]";

  return (
    <div className="grid gap-2 rounded-md border border-foreground/30 px-2.5 py-2 text-[12px]">
      <div className="grid grid-cols-2 gap-2">
        <label className="grid gap-0.5">
          <span className="text-muted-foreground">Human gene</span>
          <Input className={cn(field, "font-mono")} value={value.human_gene} onChange={(e) => set({ human_gene: e.target.value })} />
        </label>
        <label className="grid gap-0.5">
          <span className="text-muted-foreground">Fly gene</span>
          <Input className={cn(field, "font-mono italic")} value={value.fly_gene} onChange={(e) => set({ fly_gene: e.target.value })} />
        </label>
      </div>
      <label className="grid gap-0.5">
        <span className="text-muted-foreground">Clusters lost (comma separated)</span>
        <Input
          className={cn(field, "font-mono")}
          defaultValue={row.clusters.join(", ")}
          onChange={(e) => set({ clusters: e.target.value.split(",").map((c) => c.trim()).filter(Boolean) })}
        />
      </label>
      <div className="grid gap-0.5">
        <span className="text-muted-foreground">Tier</span>
        <div className="flex gap-1">
          {TIERS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => set({ tier: t })}
              className={cn("flex-1 rounded border py-0.5 text-[11px] uppercase", value.tier === t ? "border-foreground/50 bg-secondary font-medium" : "text-muted-foreground")}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <label className="grid gap-0.5">
        <span className="text-muted-foreground">Finding</span>
        <textarea
          rows={3}
          value={value.finding}
          onChange={(e) => set({ finding: e.target.value })}
          className="w-full resize-y rounded-md border border-input bg-transparent px-2 py-1.5 text-[12px] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        />
      </label>
      <div className="flex gap-1.5">
        <Button size="sm" variant="outline" className="h-7 flex-1" onClick={onApprove} disabled={busy}>
          <Check /> Approve with changes
        </Button>
        <Button size="sm" variant="ghost" className="h-7" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
      {error ? <ErrorNote error={error} /> : null}
    </div>
  );
}

function ApprovedList({ rows }: { rows: EvidenceRow[] }) {
  const changed = useEvidenceChanged();
  const remove = useMutation({ mutationFn: (id: string) => api.removeEvidence(id), onSuccess: changed });

  return (
    <div className="grid gap-1.5 border-t pt-2.5">
      <p className="text-[11.5px] font-medium text-muted-foreground">
        In the evidence table from papers ({rows.length}) · used by the next run of each gene
      </p>
      {rows.map((r) => (
        <div key={r.extracted?.id ?? `${r.citation}${r.clusters.join()}`} className="flex items-center justify-between gap-2 text-[12px]">
          <span className="min-w-0 truncate" title={r.finding}>
            <span className="font-mono">{r.human_gene}</span> · <span className="font-mono">{r.clusters.join(", ") || "no clusters"}</span>{" "}
            <span className="text-muted-foreground">· {r.citation}</span>
          </span>
          {r.extracted && (
            <Button
              size="icon-xs"
              variant="ghost"
              title="Take this row out of the evidence table"
              aria-label="Remove"
              disabled={remove.isPending}
              onClick={() => remove.mutate(r.extracted!.id)}
            >
              <Trash2 />
            </Button>
          )}
        </div>
      ))}
      {remove.error && <ErrorNote error={remove.error} />}
    </div>
  );
}
