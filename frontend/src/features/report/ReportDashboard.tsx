import { useMemo } from "react";
import { useListActionOptions, useListMetrics } from "@/api/generated/client";
import type { Report } from "@/api/generated/model";
import { BreakdownTable } from "@/features/risk/BreakdownTable";
import { BAD_YEAR_METRIC, badYearByRow, buildRows, MEASURES, transitionChoice } from "@/lib/risk";
import { keyMetrics } from "./keyMetrics";
import { ReportTile } from "./ReportTile";

const COST_METRIC = MEASURES[0]?.metric;

/** The report's key numbers and the cost by crop and climate scenario. The insights are in the text. */
export function ReportDashboard({ report }: { report: Report }) {
  const resultSetId = report.result_set_id;
  const tiles = keyMetrics(report.metrics);
  const options = useListActionOptions(resultSetId);
  const cost = useListMetrics(resultSetId, { name: COST_METRIC, limit: 5000 });
  const badYears = useListMetrics(resultSetId, { name: BAD_YEAR_METRIC, limit: 5000 });
  const rows = useMemo(
    () => buildRows(cost.data?.items ?? [], transitionChoice({}), {}),
    [cost.data],
  );
  const badByRow = useMemo(() => badYearByRow(badYears.data?.items ?? []), [badYears.data]);
  const actionName = (actionId: string | null) =>
    actionId ? options.data?.find((option) => option.action_id === actionId)?.name : undefined;

  return (
    <div className="space-y-6">
      {tiles.length > 0 ? (
        <section aria-label="Key numbers" className="grid grid-cols-4 gap-4">
          {tiles.map((metric) => (
            <ReportTile
              key={metric.metric_id}
              metric={metric}
              actionName={actionName(metric.action_id)}
            />
          ))}
        </section>
      ) : null}
      {rows.length > 0 ? (
        <section aria-label="Cost by crop and climate scenario">
          <h2 className="mb-2 font-semibold">
            Expected cost per year by crop and climate scenario
          </h2>
          <div className="overflow-x-auto border print:overflow-visible">
            <BreakdownTable rows={rows} badYears={badByRow} />
          </div>
        </section>
      ) : null}
    </div>
  );
}
