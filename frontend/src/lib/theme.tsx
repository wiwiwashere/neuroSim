"use client";

// Light/dark follows the OS until the person picks one. Charts (Plotly,
// Cytoscape) can't read CSS variables, so useChartColors() resolves the
// tokens from globals.css into hex and re-renders when the theme flips.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";

const ThemeCtx = createContext<{ theme: Theme; toggle: () => void }>({ theme: "light", toggle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("neurosim-theme");
    } catch {}
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => setTheme(stored === "light" || stored === "dark" ? stored : media.matches ? "dark" : "light");
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem("neurosim-theme", next);
      } catch {}
      return next;
    });
  }, []);

  return <ThemeCtx.Provider value={{ theme, toggle }}>{children}</ThemeCtx.Provider>;
}

export const useTheme = () => useContext(ThemeCtx);

const TOKENS = [
  "background",
  "card",
  "foreground",
  "muted-foreground",
  "faint",
  "border",
  "signal",
  "signal-soft",
  "seed",
  "seed-soft",
  "chance",
] as const;

export type ChartColors = Record<(typeof TOKENS)[number], string>;

export function useChartColors(): ChartColors | null {
  const { theme } = useTheme();
  const [colors, setColors] = useState<ChartColors | null>(null);
  useEffect(() => {
    const style = getComputedStyle(document.documentElement);
    const next = {} as ChartColors;
    for (const t of TOKENS) next[t] = style.getPropertyValue(`--${t}`).trim();
    setColors(next);
  }, [theme]);
  return colors;
}

/** hex -> rgba() with alpha, for translucent Sankey links. */
export function withAlpha(hex: string, alpha: number) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.replace(/./g, (c) => c + c) : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
