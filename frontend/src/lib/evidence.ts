import { plainNumber } from "@/lib/format";

const TOKEN = /\{\{ev:([\w.]+)\}\}/g;

function show(value: unknown): string {
  if (typeof value === "number") return plainNumber(value);
  if (value === null || value === undefined) return "";
  return String(value);
}

/** Fills the {{ev:name}} tokens of an explanation with the evidence values they cite. */
export function fillEvidenceTokens(text: string, values: Record<string, unknown>): string {
  return text.replace(TOKEN, (_match, name: string) => {
    const filled = show(values[name]);
    return filled === "" ? "(value missing)" : filled;
  });
}

export function evidenceValueText(value: unknown): string {
  return show(value);
}
