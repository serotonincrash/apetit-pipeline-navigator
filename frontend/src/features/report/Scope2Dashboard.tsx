import type { Report } from "@/api/generated/model";
import { TableSkeleton } from "@/components/TableSkeleton";
import { scope2KeyMetrics } from "@/features/report/keyMetrics";
import { ReportTile } from "@/features/report/ReportTile";
import { Scope2Table } from "@/features/scope2/Scope2Table";
import { useScope2Metrics } from "@/features/scope2/useScope2Metrics";

/** The Scope 2 totals the report cites and the table of sites by year. */
export function Scope2Dashboard({ report }: { report: Report }) {
  const tiles = scope2KeyMetrics(report.metrics);
  const metrics = useScope2Metrics(report.result_set_id);
  const hasRows = metrics.use.length + metrics.location.length + metrics.market.length > 0;
  return (
    <div className="space-y-6">
      {tiles.length > 0 ? (
        <section aria-label="Key numbers" className="grid grid-cols-4 gap-4">
          {tiles.map((metric) => (
            <ReportTile key={metric.metric_id} metric={metric} actionName={undefined} />
          ))}
        </section>
      ) : null}
      {metrics.isPending ? <TableSkeleton rows={8} /> : null}
      {hasRows ? (
        <section aria-label="Scope 2 by site and year">
          <h2 className="mb-2 font-semibold">Electricity and Scope 2 by site and year</h2>
          <div className="overflow-x-auto border print:overflow-visible">
            <Scope2Table use={metrics.use} location={metrics.location} market={metrics.market} />
          </div>
        </section>
      ) : null}
    </div>
  );
}
