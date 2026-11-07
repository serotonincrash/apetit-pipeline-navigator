import { plainNumber } from "@/lib/format";

/** An assumption's value as text. The API leaves its type open: numbers, text, lists or pairs. */
export function assumptionValue(value: unknown): string {
  if (typeof value === "number") return plainNumber(value);
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(assumptionValue).join(", ");
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, item]) => `${key.replaceAll("_", " ")} ${assumptionValue(item)}`)
      .join(", ");
  }
  return String(value);
}
