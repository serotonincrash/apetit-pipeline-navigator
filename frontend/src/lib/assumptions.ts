import { plainNumber } from "@/lib/format";

/** An assumption's value as text. The API leaves its type open: numbers, text or a list. */
export function assumptionValue(value: unknown): string {
  if (typeof value === "number") return plainNumber(value);
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return JSON.stringify(value);
}
