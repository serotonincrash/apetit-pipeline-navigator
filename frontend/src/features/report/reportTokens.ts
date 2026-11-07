import type { Insight } from "@/api/generated/model";

const TOKEN = /\{\{(metric|insight):(\w+)\}\}/g;

export type Piece =
  | { kind: "text"; text: string }
  | { kind: "metric"; id: string }
  | { kind: "insight"; id: string };

/** Splits drafted text into plain text and the metric and insight tokens that cite numbers. */
export function splitTokens(text: string): Piece[] {
  const pieces: Piece[] = [];
  let last = 0;
  for (const found of text.matchAll(TOKEN)) {
    if (found.index > last) pieces.push({ kind: "text", text: text.slice(last, found.index) });
    const id = found[2] ?? "";
    pieces.push(found[1] === "metric" ? { kind: "metric", id } : { kind: "insight", id });
    last = found.index + found[0].length;
  }
  if (last < text.length) pieces.push({ kind: "text", text: text.slice(last) });
  return pieces;
}

/** Every metric a paragraph cites, directly or through an insight, once and in reading order. */
export function citedMetricIds(text: string, insights: Insight[]): string[] {
  const ids: string[] = [];
  for (const piece of splitTokens(text)) {
    if (piece.kind === "metric") ids.push(piece.id);
    if (piece.kind === "insight") {
      const insight = insights.find((candidate) => candidate.insight_id === piece.id);
      ids.push(...(insight?.metric_ids ?? []));
    }
  }
  return [...new Set(ids)];
}
