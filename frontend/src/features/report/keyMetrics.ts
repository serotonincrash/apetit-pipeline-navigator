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
