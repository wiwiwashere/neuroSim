"use client";

// Workspace state: what the person (or the agent) has picked, and every run
// made this session. Both the left column and the agent panel write here, and
// the results tabs read from it, which is how the agent "drives the screen".

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { GroupLevel, PerturbationMode, SimulationRequest, SimulationResult } from "./types";

export type Tab = "overview" | "ranked" | "network" | "compare";

export interface RunEntry {
  key: string; // request signature; mock runs share a run_id, so we key on what was asked
  label: string;
  result: SimulationResult;
  source: "you" | "agent";
}

export const requestKey = (r: SimulationRequest) =>
  [
    r.human_gene,
    r.mode ?? "knockout",
    r.mode === "reduce_output" ? (r.strength ?? 1).toFixed(2) : "1.00",
    r.high_confidence_only ? "hc" : "all",
    (r.seed_cell_types ?? []).slice().sort().join("+"),
    r.disease ?? "",
  ].join("|");

export function runLabel(r: SimulationRequest): string {
  const mode = r.mode === "reduce_output" ? `output −${Math.round((r.strength ?? 1) * 100)}%` : "knockout";
  const seeds = r.seed_cell_types?.length ? ` · ${r.seed_cell_types.join(", ")} only` : "";
  return `${r.human_gene} · ${mode}${seeds}`;
}

interface WorkspaceState {
  disease: string | null;
  gene: string | null;
  highConfidenceOnly: boolean;
  mode: PerturbationMode;
  strength: number;
  level: GroupLevel;
  tab: Tab;
  runs: RunEntry[];
  activeKey: string | null;
  compareKey: string | null;
}

interface WorkspaceApi extends WorkspaceState {
  activeRun: RunEntry | null;
  compareRun: RunEntry | null;
  set: (patch: Partial<WorkspaceState>) => void;
  addRun: (result: SimulationResult, source: RunEntry["source"], opts?: { activate?: boolean }) => RunEntry;
}

const Ctx = createContext<WorkspaceApi | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WorkspaceState>({
    disease: null,
    gene: null,
    highConfidenceOnly: false,
    mode: "knockout",
    strength: 0.5,
    level: "super_region",
    tab: "overview",
    runs: [],
    activeKey: null,
    compareKey: null,
  });

  const set = useCallback((patch: Partial<WorkspaceState>) => setState((s) => ({ ...s, ...patch })), []);

  const addRun = useCallback<WorkspaceApi["addRun"]>((result, source, opts) => {
    const entry: RunEntry = { key: requestKey(result.request), label: runLabel(result.request), result, source };
    setState((s) => {
      const runs = [...s.runs.filter((r) => r.key !== entry.key), entry];
      return opts?.activate === false ? { ...s, runs } : { ...s, runs, activeKey: entry.key };
    });
    return entry;
  }, []);

  const value = useMemo<WorkspaceApi>(() => {
    const find = (k: string | null) => state.runs.find((r) => r.key === k) ?? null;
    return { ...state, activeRun: find(state.activeKey), compareRun: find(state.compareKey), set, addRun };
  }, [state, set, addRun]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWorkspace outside WorkspaceProvider");
  return ctx;
}
