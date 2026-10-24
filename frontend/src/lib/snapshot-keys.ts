// Maps an API path (and POST body) to a file under public/demo/.
// Shared by the app (lib/api.ts) and scripts/snapshot.mjs, so a snapshot
// written by the script is exactly the file the app asks for.

const safe = (s: string) => s.replace(/[^A-Za-z0-9._-]+/g, "_");

export function snapshotPath(path: string, body?: string): string {
  const [pathname, query = ""] = path.split("?");
  let key = safe(pathname.replace(/^\//, "").replace(/\//g, "__"));
  if (query) {
    const params = new URLSearchParams(query);
    params.sort();
    key += "--" + safe(params.toString());
  }
  if (body) {
    // POST /simulate: key on the fields that change the result, in a fixed order.
    const b = JSON.parse(body) as Record<string, unknown>;
    if (pathname === "/simulate") {
      const mode = (b.mode as string) ?? "knockout";
      const strength = mode === "knockout" ? 1 : Number(b.strength ?? 1);
      const parts = [b.human_gene, mode, strength.toFixed(2), b.high_confidence_only ? "hc" : "all"];
      const seeds = b.seed_cell_types as string[] | null | undefined;
      if (seeds?.length) parts.push([...seeds].sort().join("+"));
      key += "--" + safe(parts.join("-"));
    }
  }
  return `${key}.json`;
}
