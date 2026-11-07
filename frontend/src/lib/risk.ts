import type { Metric } from "@/api/generated/model";
import { DEFAULT_TRANSITION } from "@/lib/labels";

export type Measure = "cost" | "tail" | "emissions";

export const MEASURES: { id: Measure; label: string; metric: string }[] = [
  { id: "cost", label: "Expected cost per year", metric: "price_risk.expected_cost_eur" },
  { id: "tail", label: "1-in-10 cost", metric: "price_risk.one_in_ten_cost_eur" },
  { id: "emissions", label: "Extra emissions", metric: "price_risk.expected_import_tco2e" },
];

export const BAD_YEAR_METRIC = "project_yields.bad_year_chance";

/** Today first, then the three climate scenarios from low to high. */
export const SCENARIO_ORDER = ["baseline", "ssp126", "ssp245", "ssp585"] as const;

export interface RiskRow {
  key: string;
  crop: string;
  region: string;
  byScenario: Record<string, Metric | undefined>;
}

export type TransitionChoice = Record<string, string>;

export function transitionChoice(search: {
  ssp126?: string;
  ssp245?: string;
  ssp585?: string;
}): TransitionChoice {
  return {
    baseline: DEFAULT_TRANSITION.baseline ?? "today",
    ssp126: search.ssp126 ?? DEFAULT_TRANSITION.ssp126 ?? "",
    ssp245: search.ssp245 ?? DEFAULT_TRANSITION.ssp245 ?? "",
    ssp585: search.ssp585 ?? DEFAULT_TRANSITION.ssp585 ?? "",
  };
}

/** One row per crop and region. Each climate scenario holds the metric of its chosen transition. */
export function buildRows(
  metrics: Metric[],
  choice: TransitionChoice,
  filter: { crop?: string; region?: string },
): RiskRow[] {
  const rows = new Map<string, RiskRow>();
  for (const metric of metrics) {
    if (!metric.crop || !metric.region || !metric.scenario) continue;
    if (filter.crop && metric.crop !== filter.crop) continue;
    if (filter.region && metric.region !== filter.region) continue;
    if (metric.ngfs_scenario !== choice[metric.scenario]) continue;
    const key = `${metric.crop}|${metric.region}`;
    const row = rows.get(key) ?? {
      key,
      crop: metric.crop,
      region: metric.region,
      byScenario: {},
    };
    row.byScenario[metric.scenario] = metric;
    rows.set(key, row);
  }
  return [...rows.values()].sort(
    (a, b) => a.crop.localeCompare(b.crop) || a.region.localeCompare(b.region),
  );
}

/** The totals over all crops and regions, one metric per climate scenario. */
export function totals(metrics: Metric[], choice: TransitionChoice): Record<string, Metric> {
  const found: Record<string, Metric> = {};
  for (const metric of metrics) {
    if (metric.crop || metric.region || !metric.scenario) continue;
    if (metric.ngfs_scenario === choice[metric.scenario]) found[metric.scenario] = metric;
  }
  return found;
}

/** The chance of a bad year for each crop, region and climate scenario. */
export function badYearByRow(metrics: Metric[]): Map<string, Record<string, Metric>> {
  const found = new Map<string, Record<string, Metric>>();
  for (const metric of metrics) {
    if (!metric.crop || !metric.region || !metric.scenario) continue;
    const key = `${metric.crop}|${metric.region}`;
    const row = found.get(key) ?? {};
    const future = metric.period?.startsWith("2041") ?? false;
    const wantsFuture = metric.scenario !== "baseline";
    if (future === wantsFuture) row[metric.scenario] = metric;
    found.set(key, row);
  }
  return found;
}
