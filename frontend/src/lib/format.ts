const DISEASE_NAMES: Record<string, string> = {
  parkinsons: "Parkinson's disease",
};

export const diseaseName = (id: string) =>
  DISEASE_NAMES[id] ?? id.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const pct = (x: number, digits = 2) => `${(x * 100).toFixed(digits)}%`;

export const signed = (x: number, digits = 1) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(digits)}`;

export const int = (x: number) => x.toLocaleString("en-US");

export const LEVEL_LABEL: Record<string, string> = {
  super_region: "Super region",
  region: "Region",
  cell_type: "Cell type",
  super_class: "Super class",
};

/** Plain-language read of a z-score against random DA neurons. */
export function zPhrase(z: number) {
  if (z >= 4) return "far above chance";
  if (z >= 2) return "above chance";
  if (z > -2) return "within chance";
  return "below chance";
}

/** The single line every results view carries (Bio writes the final wording). */
export const SCOPE_LINE = "Structural dependency in the fly connectome, not a prediction of symptoms.";

/** Plain words for a Spearman rank correlation between two genes' rankings. */
export function rhoPhrase(rho: number) {
  if (rho >= 0.8) return "nearly the same regions, in the same order";
  if (rho >= 0.5) return "mostly the same regions";
  if (rho >= 0.2) return "partly the same regions";
  if (rho > -0.2) return "unrelated rankings";
  return "opposite rankings";
}
