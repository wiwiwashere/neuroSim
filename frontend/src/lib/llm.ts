"use client";

import { useQuery } from "@tanstack/react-query";
import { api, SNAPSHOT_MODE } from "./api";

/** Which model family answers the agent, summaries and paper uploads
 * (GET /agent/llm, set by NEUROSIM_LLM on the backend), so the copy names it.
 * Says "Gemma", the backend default, until the API answers. */
export function useLlm(): { name: string; model: string | null } {
  const llm = useQuery({ queryKey: ["llm"], queryFn: api.llm, enabled: !SNAPSHOT_MODE, staleTime: Infinity, retry: false });
  return { name: llm.data?.name ?? "Gemma", model: llm.data?.model ?? null };
}
