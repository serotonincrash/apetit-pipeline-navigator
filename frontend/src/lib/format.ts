// The one place numbers, euros, percentages, periods, durations and dates are written for people.

const dash = "–";

function twoSignificant(value: number): number {
  return Number(value.toPrecision(2));
}

/** Euros to two significant figures: 36400 is "€36k", 1234000 is "€1.2M". */
export function euros(value: number): string {
  const sign = value < 0 ? "-" : "";
  const rounded = twoSignificant(Math.abs(value));
  if (rounded >= 1_000_000_000) return `${sign}€${rounded / 1_000_000_000}bn`;
  if (rounded >= 1_000_000) return `${sign}€${rounded / 1_000_000}M`;
  if (rounded >= 1_000) return `${sign}€${rounded / 1_000}k`;
  return `${sign}€${rounded}`;
}

/** Tonnes of CO2e to two significant figures: 12400 is "12k". */
export function tonnes(value: number): string {
  const rounded = twoSignificant(Math.abs(value));
  const sign = value < 0 ? "-" : "";
  if (rounded >= 1_000_000) return `${sign}${rounded / 1_000_000}M`;
  if (rounded >= 1_000) return `${sign}${rounded / 1_000}k`;
  return `${sign}${rounded}`;
}

/** A value already in percent, to one decimal: 2.64 is "2.6%". */
export function percent(value: number): string {
  return `${value.toFixed(1)}%`;
}

/** A share between 0 and 1, as a percentage to one decimal: 0.126 is "12.6%". */
export function share(value: number): string {
  return percent(value * 100);
}

/** A count with thousands separators. */
export function count(value: number): string {
  return new Intl.NumberFormat("en-GB").format(value);
}

/** A plain number to a stated number of significant figures, for assumption values. */
export function plainNumber(value: number): string {
  return new Intl.NumberFormat("en-GB", { maximumSignificantDigits: 4 }).format(value);
}

/** A period such as "2041-2060", written with an en dash. */
export function period(value: string): string {
  return value.replace("-", dash);
}

const dateTime = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** An absolute date and time, for the audit trail and for finished runs. */
export function dateAndTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

/** A relative time, only for runs in progress. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)} h ago`;
}

/** A step or section duration: "0.4 s", "12 s", "2 min 5 s". */
export function duration(seconds: number): string {
  if (seconds < 0.1) return "under 0.1 s";
  if (seconds < 10) return `${seconds.toFixed(1)} s`;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${Math.round(seconds - minutes * 60)} s`;
}

// Recipe 2 adds up meter readings, so its figures keep whole units; two significant figures
// would hide its differences from the answer inventories, which are a few tonnes.
const MEASURED = /^(scope2_electricity|compare_inventory)\./;

/** A measured amount: 1438.08 is "1,438", 4.46 is "4.5", and under 0.05 is "0". */
export function measured(value: number): string {
  const digits = Math.abs(value) < 10 ? 1 : 0;
  const rounded = Number(value.toFixed(digits));
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: digits }).format(
    rounded === 0 ? 0 : rounded,
  );
}

/** A metric value in the style of its unit, without the unit. `name` picks measured amounts. */
export function metricValue(unit: string, value: number, name = ""): string {
  if (MEASURED.test(name)) return measured(value);
  if (unit.startsWith("€")) return euros(value);
  if (unit.includes("CO2e")) return tonnes(value);
  if (unit === "%") return percent(value);
  if (unit === "share") return share(value);
  return plainNumber(value);
}

/** The unit as a column header shows it. */
export function unitLabel(unit: string): string {
  if (unit === "share") return "% of seasons";
  return unit;
}

/** A metric with its range, such as "12.6% (9.0% to 15.1%)". */
export function metricWithRange(
  unit: string,
  value: number,
  low: number | null,
  high: number | null,
): string {
  const main = metricValue(unit, value);
  if (low === null || high === null) return main;
  return `${main} (${metricValue(unit, low)} to ${metricValue(unit, high)})`;
}

/** One value of a table row: whole numbers as they are, decimals to five significant figures. */
export function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(5)));
  }
  return String(value);
}

/** A range as "3.9% to 16.1%". */
export function rangeText(unit: string, low: number, high: number): string {
  return `${metricValue(unit, low)} to ${metricValue(unit, high)}`;
}

/** A value with its unit in words, for a headline: "€140k per year", "12.6% of seasons". */
export function valueWithUnit(unit: string, value: number, name = ""): string {
  const text = metricValue(unit, value, name);
  if (unit === "%") return text;
  if (unit === "share") return `${text} of seasons`;
  if (unit.startsWith("€")) return `${text}${unit.slice(1)}`;
  return `${text} ${unit}`;
}
