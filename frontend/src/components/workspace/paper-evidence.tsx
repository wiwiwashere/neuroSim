"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, FileUp, Loader2, X } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, SNAPSHOT_MODE } from "@/lib/api";
import type { EvidenceExtraction, EvidenceProposal } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ErrorNote, FlyGene, StepHeading, TierBadge } from "./primitives";

// Paper upload (POST /evidence/extract): Gemini proposes evidence rows from a
// PDF, each with its supporting quote and page, and Bio approves or rejects
// each one. Nothing proposed is used until it is approved.
export function PaperEvidence() {
  const input = useRef<HTMLInputElement>(null);
  const [extraction, setExtraction] = useState<EvidenceExtraction | null>(null);
  const extract = useMutation({ mutationFn: (file: File) => api.extractEvidence(file), onSuccess: setExtraction });

  if (SNAPSHOT_MODE) return null;

  const update = (row: EvidenceProposal) =>
    setExtraction((x) => x && { ...x, rows: x.rows.map((r) => (r.id === row.id ? row : r)) });

  return (
    <section>
      <StepHeading title="Evidence from a paper" />
      <div className="grid gap-3 rounded-lg border bg-card p-3">
        <p className="text-[12px] leading-snug text-muted-foreground">
          Upload a fly paper. Gemini proposes evidence rows with the quote behind each one, and nothing is used until Bio approves it.
        </p>
        <input
          ref={input}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) extract.mutate(file);
            e.target.value = "";
          }}
        />
        <Button variant="outline" size="sm" onClick={() => input.current?.click()} disabled={extract.isPending}>
          {extract.isPending ? <Loader2 className="animate-spin" /> : <FileUp />}
          {extract.isPending ? "Gemini is reading the paper…" : "Upload a PDF"}
        </Button>
        {extract.error && <ErrorNote error={extract.error} />}

        {extraction && !extract.isPending && (
          <div className="grid gap-2">
            <div className="text-[12px] text-muted-foreground">
              {extraction.citation || extraction.file} ·{" "}
              {extraction.rows.length ? `${extraction.rows.length} proposed row${extraction.rows.length > 1 ? "s" : ""}` : "no neuron-loss findings found"}
            </div>
            {extraction.rows.map((row) => (
              <ProposalCard key={row.id} row={row} onDecided={update} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function ProposalCard({ row, onDecided }: { row: EvidenceProposal; onDecided: (row: EvidenceProposal) => void }) {
  const decide = useMutation({ mutationFn: (approve: boolean) => api.decideEvidence(row.id, approve), onSuccess: onDecided });
  const decided = row.status !== "pending";

  return (
    <div className={cn("grid gap-1.5 rounded-md border px-2.5 py-2", row.status === "rejected" && "opacity-55")}>
      <div className="flex items-center justify-between gap-2 text-[12.5px]">
        <span>
          <span className="font-medium">{row.human_gene}</span> → <FlyGene>{row.fly_gene}</FlyGene>
          <span className="text-muted-foreground"> · {row.model_type}</span>
        </span>
        <TierBadge tier={row.tier} />
      </div>
      <div className="text-[12px]">
        <span className="text-muted-foreground">Lost: </span>
        <span className="font-mono">{row.clusters.join(", ") || "not named"}</span>
      </div>
      <p className="text-[12.5px] leading-snug">{row.finding}</p>
      <blockquote className="border-l-2 pl-2 text-[12px] leading-snug text-muted-foreground italic">
        “{row.quote}” <span className="not-italic text-faint">p. {row.page}</span>
      </blockquote>
      <p className="text-[11.5px] leading-snug text-faint">Tier: {row.tier_reason}</p>
      {decided ? (
        <div className={cn("text-[12px] font-medium", row.status === "approved" ? "text-signal" : "text-muted-foreground")}>
          {row.status === "approved" ? "Approved, saved to the evidence table (unverified until figures are checked)" : "Rejected"}
        </div>
      ) : (
        <div className="flex gap-2 pt-0.5">
          <Button size="sm" variant="outline" className="h-7 flex-1" onClick={() => decide.mutate(true)} disabled={decide.isPending}>
            <Check /> Approve
          </Button>
          <Button size="sm" variant="ghost" className="h-7 flex-1" onClick={() => decide.mutate(false)} disabled={decide.isPending}>
            <X /> Reject
          </Button>
        </div>
      )}
      {decide.error && <ErrorNote error={decide.error} />}
    </div>
  );
}
