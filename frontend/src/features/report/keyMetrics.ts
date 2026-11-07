import type { Metric } from "@/api/generated/model";

/** The headline numbers of the dashboard, in order. The first one found for each name is shown. */
const TILE_NAMES = [
  "price_risk.expected_cost_eur",
  "price_risk.one_in_ten_cost_eur",
  "compare_actions.risk_removed_eur",
  "price_risk.expected_import_tco2e",
];

/** At most four cited metrics, one per measure, preferring the highest-emissions scenario. */
export function keyMetrics(metrics: Record<string, Metric>): Metric[] {
  const all = Object.values(metrics);
  return TILE_NAMES.flatMap((name) => {
    const named = all.filter((metric) => metric.name === name);
    const found = named.find((metric) => metric.scenario === "ssp585") ?? named[0];
    return found ? [found] : [];
  });
}

const SCOPE2_TILE_NAMES = [
  "scope2_electricity.electricity_use_mwh",
  "scope2_electricity.location_based_tco2e",
  "scope2_electricity.market_based_tco2e",
];

/** The whole-company totals of the newest year the report cites, one per measure. */
export function scope2KeyMetrics(metrics: Record<string, Metric>): Metric[] {
  const totals = Object.values(metrics).filter(
    (metric) => metric.site === null && SCOPE2_TILE_NAMES.includes(metric.name),
  );
  const newest = totals
    .map((metric) => metric.period ?? "")
    .sort()
    .at(-1);
  return SCOPE2_TILE_NAMES.flatMap((name) => {
    const found = totals.find((metric) => metric.name === name && (metric.period ?? "") === newest);
    return found ? [found] : [];
  });
}
