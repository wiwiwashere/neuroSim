"use client";

import { Moon, Sun } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SNAPSHOT_MODE } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";

function Mark() {
  // Two neurons and a synapse: the product in one glyph.
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
      <circle cx="6" cy="8" r="3" className="fill-seed" />
      <circle cx="18" cy="16" r="3" className="fill-signal" />
      <path d="M8.5 9.5 C 12 10, 12 14, 15.5 14.5" className="fill-none stroke-foreground" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function TopBar() {
  const ws = useWorkspace();
  const { theme, toggle } = useTheme();
  const steps = [
    { label: "Gene", done: !!ws.gene, go: () => {} },
    { label: "Chain", done: !!ws.gene, go: () => {} },
    { label: "Results", done: !!ws.activeRun, go: () => ws.activeRun && ws.set({ tab: "overview" }) },
    { label: "Compare", done: !!ws.compareRun, go: () => ws.set({ tab: "compare" }) },
  ];
  const current = steps.findIndex((s) => !s.done);
  const mock = ws.activeRun?.result.run_id.startsWith("mock-");

  return (
    <header className="flex h-12 items-center gap-6 border-b bg-card px-4">
      <div className="flex items-center gap-2">
        <Mark />
        <span className="text-[15px] font-semibold tracking-tight">neuroSim</span>
        <span className="hidden text-[12px] text-faint lg:inline">disease gene → fly connectome</span>
      </div>

      <nav aria-label="Progress" className="flex items-center gap-1 text-[12.5px]">
        {steps.map((s, i) => (
          <button
            key={s.label}
            onClick={s.go}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-1 transition-colors hover:bg-secondary",
              i === current ? "text-foreground" : s.done ? "text-muted-foreground" : "text-faint",
            )}
          >
            <span
              className={cn(
                "grid size-4 place-items-center rounded-full border font-mono text-[9.5px]",
                s.done ? "border-foreground bg-foreground text-background" : i === current ? "border-foreground" : "border-faint/60",
              )}
            >
              {i + 1}
            </span>
            {s.label}
            {i < steps.length - 1 && <span className="ml-1 text-faint">/</span>}
          </button>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        {mock && (
          <Tooltip>
            <TooltipTrigger className="rounded-md border border-dashed px-2 py-0.5 text-[11px] text-muted-foreground">
              sample numbers
            </TooltipTrigger>
            <TooltipContent className="max-w-60">The API is serving its mock payloads (NEUROSIM_MOCKS=1). Every number is fake.</TooltipContent>
          </Tooltip>
        )}
        {SNAPSHOT_MODE && (
          <span className="rounded-md bg-seed-soft px-2 py-0.5 text-[11px] font-medium text-foreground">snapshot mode</span>
        )}
        <button onClick={toggle} aria-label="Toggle theme" className="grid size-8 place-items-center rounded-md hover:bg-secondary">
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>
      </div>
    </header>
  );
}
