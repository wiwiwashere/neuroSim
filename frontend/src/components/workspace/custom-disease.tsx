"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Download, FileUp, Loader2, Plus, Sparkles, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, customTemplateUrl, SNAPSHOT_MODE } from "@/lib/api";
import type { AffectedCheck, CustomDisease, CustomRow, CustomRowChecks, CustomRowInput, EvidenceTier } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { ConfidenceMeter, ErrorNote, FlyGene, USER_SUPPLIED_LABEL } from "./primitives";

// A disease of the person's own (POST /custom/preview, POST /custom/diseases):
// a CSV/JSON file or rows typed in, each row = one gene and the fly neurons it
// affects (dopamine clusters or FlyWire cell types). Every row is checked the
// way paper rows are (ortholog, each name resolved with its neuron count,
// duplicates, confidence) and shown for review; nothing is saved while a row
// has a problem. Saved diseases join the picker tagged "your data" and run
// through the same pipeline; every view labels their rows user-supplied.

/** The saved user-added diseases, shared by the picker and the chain. */
export function useCustomDiseases() {
  return useQuery({ queryKey: ["custom-diseases"], queryFn: api.customDiseases, enabled: !SNAPSHOT_MODE });
}

/** The chosen disease's id when it is user-added (the chain and runs then ask for its rows only), else undefined. */
export function useCustomDiseaseId(): string | undefined {
  const ws = useWorkspace();
  const custom = useCustomDiseases();
  return ws.disease && custom.data?.some((d) => d.id === ws.disease) ? ws.disease : undefined;
}

/** After a save or removal, everything that reads the evidence table is stale. */
export function useCustomChanged() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["custom-diseases", "diseases", "genes", "chain", "targets"]) qc.invalidateQueries({ queryKey: [key] });
  };
}

interface Draft {
  key: number;
  human_gene: string;
  fly_gene: string;
  affected: string;
  tier: EvidenceTier;
  model_type: string;
  finding: string;
  citation: string;
  url: string;
  checks?: CustomRowChecks;
}

let nextKey = 1;
const blank = (): Draft => ({
  key: nextKey++,
  human_gene: "",
  fly_gene: "",
  affected: "",
  tier: "medium",
  model_type: "other",
  finding: "",
  citation: "",
  url: "",
});

const fromServer = (r: CustomRow): Draft => ({
  key: nextKey++,
  human_gene: r.human_gene,
  fly_gene: r.fly_gene,
  affected: r.affected.join("; "),
  tier: r.tier,
  model_type: r.model_type,
  finding: r.finding,
  citation: r.citation,
  url: r.url,
  checks: r.checks,
});

const toInput = (d: Draft): CustomRowInput => ({
  human_gene: d.human_gene,
  fly_gene: d.fly_gene,
  affected: d.affected,
  tier: d.tier,
  model_type: d.model_type,
  finding: d.finding,
  citation: d.citation,
  url: d.url,
});

const TIERS: EvidenceTier[] = ["high", "medium", "low"];
const MODELS = ["mutant", "RNAi", "overexpression", "other"];

export function CustomDiseasePanel({ onClose, onSaved }: { onClose: () => void; onSaved: (d: CustomDisease) => void }) {
  const [name, setName] = useState("");
  const [file, setFile] = useState("typed in");
  const [rows, setRows] = useState<Draft[]>([blank()]);
  const [stale, setStale] = useState(true); // edited since the last check
  const [problems, setProblems] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const changed = useCustomChanged();

  const applyPreview = (out: { disease: { name: string }; rows: CustomRow[]; problems: string[]; file: string }) => {
    if (out.disease.name) setName(out.disease.name);
    setRows(out.rows.map(fromServer));
    setProblems(out.problems);
    setStale(false);
  };
  const preview = useMutation({ mutationFn: api.previewCustom, onSuccess: applyPreview });
  const save = useMutation({
    mutationFn: () => api.saveCustom({ name, file, rows: rows.map(toInput) }),
    onSuccess: (saved) => {
      changed();
      onSaved(saved);
    },
  });

  const edit = (key: number, patch: Partial<Draft>) => {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
    setStale(true);
  };
  const remove = (key: number) => {
    setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.key !== key) : [blank()]));
    setStale(true);
  };
  const upload = (f: File) => {
    setFile(f.name);
    preview.mutate({ file: f, disease: name || undefined });
  };
  const check = () => preview.mutate({ rows: rows.map(toInput), disease: name || undefined });
  // "Use the example": the server's example rows (real FlyWire names that pass
  // every check) fill the form and are checked at once, so Save is one click away.
  const example = useMutation({
    mutationFn: async () => {
      const tmpl = await api.customTemplate();
      const drafts = tmpl.rows.map((r) => ({ ...blank(), ...r, affected: r.affected.join("; "), tier: r.tier || "medium", model_type: r.model_type || "other" }) as Draft);
      setName(tmpl.disease);
      setFile("example");
      setRows(drafts);
      return api.previewCustom({ rows: drafts.map(toInput), disease: tmpl.disease });
    },
    onSuccess: applyPreview,
  });

  const busy = preview.isPending || save.isPending || example.isPending;
  const rowProblems = rows.some((r) => r.checks?.problems.length);
  const canSave = !stale && !busy && problems.length === 0 && !rowProblems && rows.every((r) => r.checks?.can_seed);

  return (
    <div className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-3 rounded-lg border border-seed/50 bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[13px] font-medium">Add your own disease</p>
          <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">
            One row per gene: which fly neurons it affects, as dopamine clusters (PPL1, PAM, PPM3…) or FlyWire cell types
            (MBON01, KCg-m…). Saved rows are tagged “{USER_SUPPLIED_LABEL}” everywhere they appear.
          </p>
        </div>
        <Button size="icon-xs" variant="ghost" onClick={onClose} aria-label="Close" disabled={busy}>
          <X />
        </Button>
      </div>

      <input
        ref={input}
        type="file"
        accept=".csv,.json,text/csv,application/json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload(f);
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
          const f = e.dataTransfer.files?.[0];
          if (f) upload(f);
        }}
        className={cn(
          "flex flex-col items-center gap-1 rounded-md border border-dashed px-3 py-3 text-[12.5px] text-muted-foreground transition-colors",
          dragging ? "border-foreground/60 bg-secondary" : "hover:border-foreground/40",
          busy && "opacity-60",
        )}
      >
        <FileUp className="size-4" />
        Drop a CSV or JSON file here, or type the rows below
        <span className="flex items-center gap-2 text-[11px] text-faint">
          <span
            role="button"
            tabIndex={0}
            className="inline-flex items-center gap-0.5 text-seed underline-offset-2 hover:underline"
            title="Fill the form with example rows (Huntington's disease, HTT → htt, real FlyWire names) and check them"
            onClick={(e) => {
              e.stopPropagation();
              if (!busy) example.mutate();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                e.stopPropagation();
                if (!busy) example.mutate();
              }
            }}
          >
            {example.isPending ? <Loader2 className="size-3 animate-spin" /> : <Sparkles className="size-3" />} Use the example
          </span>
          · Template:
          <a href={customTemplateUrl("csv")} download className="inline-flex items-center gap-0.5 underline-offset-2 hover:text-foreground hover:underline" onClick={(e) => e.stopPropagation()}>
            <Download className="size-3" /> CSV
          </a>
          <a href={customTemplateUrl("json")} download className="inline-flex items-center gap-0.5 underline-offset-2 hover:text-foreground hover:underline" onClick={(e) => e.stopPropagation()}>
            <Download className="size-3" /> JSON
          </a>
        </span>
      </button>

      <label className="grid gap-0.5 text-[12px]">
        <span className="text-muted-foreground">Disease name</span>
        <Input
          className="h-8 text-[12.5px]"
          value={name}
          placeholder="Huntington's disease"
          onChange={(e) => {
            setName(e.target.value);
            setStale(true);
          }}
        />
      </label>

      <div className="grid gap-2">
        {rows.map((row, i) => (
          <RowCard key={row.key} row={row} index={i} stale={stale} busy={busy} onChange={(patch) => edit(row.key, patch)} onRemove={() => remove(row.key)} />
        ))}
        <Button
          size="sm"
          variant="ghost"
          className="h-7 justify-start text-[12px]"
          disabled={busy}
          onClick={() => {
            setRows((rs) => [...rs, blank()]);
            setStale(true);
          }}
        >
          <Plus /> Add a row
        </Button>
      </div>

      {problems.length > 0 && (
        <ul className="grid gap-0.5">
          {problems.map((p) => (
            <li key={p} className="flex gap-1.5 text-[11.5px] leading-snug text-destructive">
              <AlertTriangle className="mt-px size-3 shrink-0" />
              {p}
            </li>
          ))}
        </ul>
      )}
      {preview.error && <ErrorNote error={preview.error} />}
      {example.error && <ErrorNote error={example.error} />}
      {save.error && <ErrorNote error={save.error} />}

      <div className="flex items-center gap-1.5">
        <Button size="sm" variant="outline" className="h-8 flex-1" onClick={check} disabled={busy || !rows.some((r) => r.human_gene.trim())}>
          {preview.isPending ? <Loader2 className="animate-spin" /> : null}
          {stale ? "Check rows" : "Check again"}
        </Button>
        <Button size="sm" className="h-8 flex-1" onClick={() => save.mutate()} disabled={!canSave} title={stale ? "Check the rows first" : undefined}>
          {save.isPending ? <Loader2 className="animate-spin" /> : <Check />}
          Save disease
        </Button>
      </div>
      <p className="text-[11px] leading-snug text-faint">
        Saved to <span className="font-mono">data/custom_diseases.json</span> on this machine only; never into the curated
        table. The engine’s random baseline draws dopamine neurons whatever the seeds are.
      </p>
    </div>
  );
}

function RowCard({
  row,
  index,
  stale,
  busy,
  onChange,
  onRemove,
}: {
  row: Draft;
  index: number;
  stale: boolean;
  busy: boolean;
  onChange: (patch: Partial<Draft>) => void;
  onRemove: () => void;
}) {
  const field = "h-7 text-[12px]";
  const checks = stale ? undefined : row.checks;
  const listId = `affected-names-${row.key}`;
  // Autocomplete on the name being typed (the text after the last ;).
  const typing = row.affected.split(/[;|]/).pop()?.trim() ?? "";
  const names = useQuery({
    queryKey: ["custom-names", typing],
    queryFn: () => api.customNames(typing),
    enabled: typing.length >= 2,
    staleTime: 60_000,
  });
  const prefix = row.affected.includes(";") ? row.affected.slice(0, row.affected.lastIndexOf(";") + 1) + " " : "";
  const flyPlaceholder = checks?.ortholog.known ? checks.ortholog.fly_genes.join(", ") : "only if the gene isn't in our table";

  return (
    <div className={cn("grid gap-1.5 rounded-md border px-2.5 py-2 text-[12px]", checks?.problems.length ? "border-destructive/40" : "")}>
      <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
        <label className="grid gap-0.5">
          <span className="text-muted-foreground">Human gene</span>
          <Input className={cn(field, "font-mono")} value={row.human_gene} placeholder="HTT" onChange={(e) => onChange({ human_gene: e.target.value.toUpperCase() })} />
        </label>
        <label className="grid gap-0.5">
          <span className="text-muted-foreground">Fly gene</span>
          <Input className={cn(field, "font-mono italic")} value={row.fly_gene} placeholder={flyPlaceholder} onChange={(e) => onChange({ fly_gene: e.target.value })} />
        </label>
        <Button size="icon-xs" variant="ghost" onClick={onRemove} aria-label={`Remove row ${index + 1}`} disabled={busy}>
          <Trash2 />
        </Button>
      </div>
      <label className="grid gap-0.5">
        <span className="text-muted-foreground">Affected neurons (clusters or cell types, separated by ;)</span>
        <Input
          className={cn(field, "font-mono")}
          value={row.affected}
          list={listId}
          placeholder="PAM; MBON01"
          autoComplete="off"
          onChange={(e) => onChange({ affected: e.target.value })}
        />
        <datalist id={listId}>
          {(names.data ?? []).map((n) => (
            <option key={n.name} value={`${prefix}${n.name}`}>
              {n.kind === "cluster" ? "cluster" : "cell type"}
              {n.n_neurons !== null ? ` · ${n.n_neurons} neurons` : ""}
              {n.kind === "cell_type" && !n.dopamine ? " · not dopamine" : ""}
            </option>
          ))}
        </datalist>
      </label>
      {checks && (
        <div className="flex flex-wrap items-center gap-1">
          {checks.affected.map((a) => (
            <AffectedChip key={a.name} check={a} onPick={(name) => onChange({ affected: replaceName(row.affected, a.name, name) })} />
          ))}
          {checks.confidence !== null && <ConfidenceMeter value={checks.confidence} className="ml-auto" />}
        </div>
      )}
      <div className="grid grid-cols-[auto_1fr] items-center gap-2">
        <div className="flex gap-1">
          {TIERS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => onChange({ tier: t })}
              className={cn("rounded border px-1.5 py-0.5 text-[10.5px] uppercase", row.tier === t ? "border-foreground/50 bg-secondary font-medium" : "text-muted-foreground")}
            >
              {t}
            </button>
          ))}
        </div>
        <select
          value={row.model_type}
          onChange={(e) => onChange({ model_type: e.target.value })}
          className="h-7 rounded-md border border-input bg-transparent px-1.5 text-[12px] text-muted-foreground outline-none"
          aria-label="Fly model type"
        >
          {MODELS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <details className="text-muted-foreground" open={!!(row.finding || row.citation)}>
        <summary className="cursor-pointer text-[11.5px] select-none hover:text-foreground">Finding and source (optional)</summary>
        <div className="mt-1.5 grid gap-1.5">
          <Input className={field} value={row.finding} placeholder="One sentence: what was found" onChange={(e) => onChange({ finding: e.target.value })} />
          <div className="grid grid-cols-2 gap-1.5">
            <Input className={field} value={row.citation} placeholder="Smith et al. 2020, or your own data" onChange={(e) => onChange({ citation: e.target.value })} />
            <Input className={field} value={row.url} placeholder="https://doi.org/…" onChange={(e) => onChange({ url: e.target.value })} />
          </div>
        </div>
      </details>
      {checks && (
        <ul className="grid gap-0.5">
          {checks.ortholog.known && checks.ortholog.fly_genes.length > 0 && (
            <li className="text-[11.5px] leading-snug text-muted-foreground">
              Fly ortholog from our table:{" "}
              {checks.ortholog.fly_genes.map((f, i) => (
                <span key={f}>
                  {i > 0 && ", "}
                  <FlyGene>{f}</FlyGene>
                </span>
              ))}
            </li>
          )}
          {checks.problems.map((p) => (
            <li key={p} className="flex gap-1.5 text-[11.5px] leading-snug text-destructive">
              <AlertTriangle className="mt-px size-3 shrink-0" />
              {p}
            </li>
          ))}
          {checks.notes.map((n) => (
            <li key={n} className="text-[11.5px] leading-snug text-muted-foreground">
              {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Swap one name in the ; separated list for a suggestion. */
function replaceName(affected: string, from: string, to: string) {
  return affected
    .split(/[;|]/)
    .map((p) => (p.trim().toLowerCase() === from.toLowerCase() ? to : p.trim()))
    .filter(Boolean)
    .join("; ");
}

function AffectedChip({ check: a, onPick }: { check: AffectedCheck; onPick: (name: string) => void }) {
  const title =
    a.kind === "cluster"
      ? `dopamine cluster · ${a.n_cell_types} cell types${a.n_neurons !== null ? ` · ${a.n_neurons} neurons` : ""}`
      : a.kind === "cell_type"
        ? `FlyWire cell type · ${a.n_neurons} neurons${a.dopamine ? " · dopamine" : " · not dopamine"}`
        : a.kind === "unchecked"
          ? "can't be checked without the connectome on this machine"
          : "not a cluster or a FlyWire cell type";
  return (
    <span className="inline-flex items-center gap-1">
      <span
        title={title}
        className={cn(
          "rounded px-1 font-mono text-[11px]",
          a.kind === "cluster" && "bg-secondary",
          a.kind === "cell_type" && "border",
          a.kind === "unchecked" && "border border-dashed text-muted-foreground",
          a.kind === "unknown" && "text-destructive line-through",
        )}
      >
        {a.name}
      </span>
      {a.kind === "cell_type" && a.n_neurons !== null && <span className="text-[10.5px] text-faint">{a.n_neurons}</span>}
      {a.suggestions.map((s) => (
        <button key={s} type="button" onClick={() => onPick(s)} className="rounded border border-dashed px-1 font-mono text-[11px] text-muted-foreground hover:text-foreground" title={`Use ${s} instead`}>
          {s}?
        </button>
      ))}
    </span>
  );
}
