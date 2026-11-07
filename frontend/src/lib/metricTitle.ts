import type { Metric } from "@/api/generated/model";
import { valueWithUnit } from "@/lib/format";
import { climateLabel, cropLabel, measureLabel, regionLabel, transitionLabel } from "@/lib/labels";

/** A metric in one line: its measure, where it applies and its value. */
export function metricTitle(metric: Metric): string {
  const place = [metric.crop && cropLabel(metric.crop), metric.region && regionLabel(metric.region)]
    .filter(Boolean)
    .join(", ");
  const where = place || "All crops and regions";
  const scenario = [
    metric.scenario && climateLabel(metric.scenario),
    metric.ngfs_scenario && transitionLabel(metric.ngfs_scenario),
  ]
    .filter(Boolean)
    .join(", ");
  return [
    measureLabel(metric.name),
    where,
    scenario,
    valueWithUnit(metric.unit, metric.value, metric.name),
  ]
    .filter(Boolean)
    .join(". ");
}
