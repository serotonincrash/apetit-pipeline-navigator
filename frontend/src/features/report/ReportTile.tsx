import type { Metric } from "@/api/generated/model";
import { MetricNumber } from "@/components/MetricNumber";
import { unitLabel } from "@/lib/format";
import { climateLabel, measureLabel, transitionLabel } from "@/lib/labels";

interface ReportTileProps {
  metric: Metric;
  /** The option that earns the number, for numbers about an action. */
  actionName: string | undefined;
}

/** One headline number of the report, with what it measures and where it applies. */
export function ReportTile({ metric, actionName }: ReportTileProps) {
  const where = [
    actionName,
    metric.scenario && climateLabel(metric.scenario),
    metric.ngfs_scenario && transitionLabel(metric.ngfs_scenario),
    metric.period,
  ].filter(Boolean);
  return (
    <div className="border-l pl-3">
      <p className="text-2xl font-semibold">
        <MetricNumber metric={metric} showRange />
      </p>
      <p className="font-medium">{measureLabel(metric.name)}</p>
      <p className="text-muted-foreground">{unitLabel(metric.unit)}</p>
      <p className="text-muted-foreground">{where.join(", ")}</p>
    </div>
  );
}
