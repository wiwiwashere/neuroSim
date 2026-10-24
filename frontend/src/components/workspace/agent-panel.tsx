"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, FlaskConical, GitCompareArrows, Loader2, Microscope, Route, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, ApiError, SNAPSHOT_MODE } from "@/lib/api";
import { standInChat } from "@/lib/standin-agent";
import type { ChatMessage, SimulationRequest, SimulationResult, ToolCall } from "@/lib/types";
import { cn } from "@/lib/utils";
import { requestKey, runLabel, useWorkspace } from "@/lib/workspace";

interface Turn {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  standIn?: boolean;
  error?: boolean;
}

const SUGGESTIONS = [
  "What if they only lose half their output?",
  "Test PPL101 alone",
  "Compare PINK1 and PRKN",
  "Why these neurons?",
];

function chipText(call: ToolCall): string {
  const i = call.input as Record<string, unknown>;
  switch (call.name) {
    case "run_simulation": {
      const req = { human_gene: String(i.human_gene), mode: i.mode, strength: i.strength, seed_cell_types: i.seed_cell_types } as SimulationRequest;
      return `ran simulation: ${runLabel(req).replace(" · ", ", ")}`;
    }
    case "compare_runs":
      return "compared the two runs";
    case "get_gene_chain":
      return `read mapping chain: ${i.human_gene}`;
    case "explain_neuron":
      return `explained neuron ${i.root_id}`;
    case "list_diseases":
      return "listed diseases";
    default:
      return call.name;
  }
}

const CHIP_ICON: Record<string, typeof FlaskConical> = {
  run_simulation: FlaskConical,
  compare_runs: GitCompareArrows,
  get_gene_chain: Route,
  explain_neuron: Microscope,
};

export function AgentPanel() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  // Load what the agent produced into the main views: the screen visibly changes.
  const loadResults = (results: SimulationResult[], compare: boolean) => {
    if (!results.length) return;
    const entries = results.map((r) => ws.addRun(r, "agent", { activate: false }));
    if (compare && entries.length >= 2) {
      ws.set({ activeKey: entries[0].key, compareKey: entries[1].key, tab: "compare" });
    } else {
      const req = results[results.length - 1].request;
      ws.set({
        activeKey: entries[entries.length - 1].key,
        gene: req.human_gene,
        disease: results[results.length - 1].seeds.disease,
        mode: req.mode ?? "knockout",
        ...(req.mode === "reduce_output" ? { strength: req.strength ?? 1 } : {}),
        tab: "overview",
      });
    }
  };

  const chat = useMutation({
    mutationFn: async (history: ChatMessage[]) => {
      if (!SNAPSHOT_MODE) {
        try {
          const reply = await api.agentChat(history);
          const results = await Promise.all(
            reply.run_ids.map((id) => qc.fetchQuery({ queryKey: ["run", id], queryFn: () => api.run(id) })),
          );
          return { ...reply, results, standIn: false };
        } catch (e) {
          // Only fall back while the endpoint is unimplemented, not on real agent errors.
          if (!(e instanceof ApiError && e.status >= 500)) throw e;
        }
      }
      return { ...(await standInChat(history, ws.activeRun?.result.request ?? null)), standIn: true };
    },
    onSuccess: (reply) => {
      setTurns((t) => [...t, { role: "assistant", content: reply.reply, toolCalls: reply.tool_calls, standIn: reply.standIn }]);
      loadResults(reply.results, reply.tool_calls.some((c) => c.name === "compare_runs"));
    },
    onError: (e) => setTurns((t) => [...t, { role: "assistant", content: e instanceof Error ? e.message : String(e), error: true }]),
  });

  const send = (text: string) => {
    const content = text.trim();
    if (!content || chat.isPending) return;
    const next = [...turns.filter((t) => !t.error), { role: "user" as const, content }];
    setTurns((t) => [...t, { role: "user", content }]);
    setDraft("");
    chat.mutate(next.map(({ role, content }) => ({ role, content })));
  };

  const openChip = (call: ToolCall) => {
    if (call.name === "run_simulation") {
      const i = call.input as unknown as SimulationRequest;
      const key = requestKey(i);
      if (ws.runs.some((r) => r.key === key)) ws.set({ activeKey: key, tab: "overview" });
    } else if (call.name === "compare_runs") {
      ws.set({ tab: "compare" });
    } else if (call.name === "get_gene_chain") {
      ws.set({ gene: String((call.input as Record<string, unknown>).human_gene) });
    }
  };

  return (
    <aside className="flex h-[560px] min-h-0 flex-col border-t bg-card lg:col-span-2 xl:col-span-1 xl:h-auto xl:border-t-0 xl:border-l">
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <Sparkles className="size-4 text-signal" />
        <h2 className="text-[13px] font-medium">Ask neuroSim</h2>
        <span className="ml-auto text-[11px] text-faint">answers only from tool results</span>
      </div>

      <div ref={scroller} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          <div className="space-y-3 pt-2">
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              Ask a what-if. The agent runs real experiments through the same API, and every result it uses shows up as a chip
              you can click.
            </p>
            <div className="grid gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-lg border px-3 py-2 text-left text-[12.5px] transition-colors hover:border-foreground/25 hover:bg-secondary/50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="ml-8 rounded-xl rounded-br-sm bg-secondary px-3 py-2 text-[13px]">
              {t.content}
            </div>
          ) : (
            <div key={i} className="space-y-2">
              {t.toolCalls && t.toolCalls.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {t.toolCalls.map((c, j) => {
                    const Icon = CHIP_ICON[c.name] ?? FlaskConical;
                    return (
                      <button
                        key={j}
                        onClick={() => openChip(c)}
                        className="inline-flex items-center gap-1.5 rounded-full border border-signal/40 bg-signal-soft px-2.5 py-1 text-[11.5px] text-foreground transition-colors hover:border-signal"
                      >
                        <Icon className="size-3 text-signal" />
                        {chipText(c)}
                      </button>
                    );
                  })}
                </div>
              )}
              <p className={cn("text-[13px] leading-relaxed", t.error && "text-destructive")}>{t.content}</p>
              {t.standIn && (
                <Tooltip>
                  <TooltipTrigger className="text-[10.5px] text-faint underline decoration-dotted underline-offset-2">
                    scripted stand-in
                  </TooltipTrigger>
                  <TooltipContent className="max-w-64">
                    {SNAPSHOT_MODE
                      ? "Snapshot mode: replies come from a scripted stand-in that reads the saved demo results."
                      : "POST /agent/chat isn’t implemented yet, so a scripted stand-in called the same API tools instead of the LLM."}
                  </TooltipContent>
                </Tooltip>
              )}
            </div>
          ),
        )}
        {chat.isPending && (
          <p className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" /> running tools…
          </p>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
        className="border-t p-3"
      >
        <div className="flex items-end gap-2 rounded-xl border bg-background px-3 py-2 focus-within:border-foreground/30">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
            rows={2}
            placeholder={ws.activeRun ? `What if… (about ${ws.activeRun.label})` : "What if…"}
            className="max-h-32 min-h-[2.5rem] flex-1 resize-none bg-transparent text-[13px] outline-none placeholder:text-faint"
          />
          <button
            type="submit"
            disabled={!draft.trim() || chat.isPending}
            aria-label="Send"
            className="mb-0.5 grid size-7 place-items-center rounded-full bg-primary text-primary-foreground disabled:opacity-30"
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </form>
    </aside>
  );
}
