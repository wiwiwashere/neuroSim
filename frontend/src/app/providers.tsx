"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";
import { WorkspaceProvider } from "@/lib/workspace";

export function Providers({ children }: { children: ReactNode }) {
  // Results are deterministic per request, so cached data never goes stale.
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: 1, refetchOnWindowFocus: false } } }),
  );
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <TooltipProvider delayDuration={150}>
          <WorkspaceProvider>{children}</WorkspaceProvider>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
