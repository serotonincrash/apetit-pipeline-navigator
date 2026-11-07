import { type DotPoint, DotRowChart } from "@/components/charts/DotRowChart";
import { ScenarioLegend } from "@/components/charts/ScenarioLegend";
import { metricValue, metricWithRange } from "@/lib/format";
import { climateLabel, placeLabel } from "@/lib/labels";
import type { RiskRow } from "@/lib/risk";
import { SCENARIO_ORDER } from "@/lib/risk";

/** Each crop and region as a row: a hollow dot for today and a dot for each climate scenario. */
export function RiskChart({
  rows,
  onOpenSources,
}: {
  rows: RiskRow[];
  onOpenSources: (id: string) => void;
}) {
  const points: DotPoint[] = rows.flatMap((row, rowIndex) =>
    SCENARIO_ORDER.flatMap((scenario) => {
      const metric = row.byScenario[scenario];
      if (!metric) return [];
      return [
        {
          rowIndex,
          value: metric.value,
          scenario,
          metricId: metric.metric_id,
          text: `${climateLabel(scenario)}: ${metricWithRange(metric.unit, metric.value, metric.low, metric.high)}`,
        },
      ];
    }),
  );
  const unit = rows.flatMap((row) => Object.values(row.byScenario)).find(Boolean)?.unit ?? "";
  return (
    <div>
      <ScenarioLegend scenarios={[...SCENARIO_ORDER]} />
      <DotRowChart
        rowLabels={rows.map((row) => placeLabel(row.crop, row.region))}
        points={points}
        formatValue={(value) => metricValue(unit, value)}
        onPointClick={onOpenSources}
      />
    </div>
  );
}
