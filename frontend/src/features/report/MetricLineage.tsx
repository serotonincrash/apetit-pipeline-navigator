import { useGetMetricSources } from "@/api/generated/client";
import { AssumptionsList } from "@/components/AssumptionsList";
import { CorrectionsList } from "@/components/CorrectionsList";
import { ErrorState } from "@/components/ErrorState";
import { LineageTableRows } from "@/components/LineageTableRows";
import { TableSkeleton } from "@/components/TableSkeleton";
import { metricTitle } from "@/lib/metricTitle";

/** Where one number comes from: its tables and filter, the corrections and the assumptions. */
export function MetricLineage({ metricId }: { metricId: string }) {
  const sources = useGetMetricSources(metricId);
  if (sources.isPending) return <TableSkeleton rows={4} />;
  if (sources.isError || !sources.data) {
    return (
      <ErrorState
        title="The sources of this number did not load."
        message="Try again."
        onRetry={() => void sources.refetch()}
      />
    );
  }
  const { metric, sources: tables, corrections, assumptions } = sources.data;
  return (
    <article className="space-y-3">
      <h3 className="text-base font-semibold">{metricTitle(metric)}</h3>
      {tables.map((table) => (
        <LineageTableRows key={table.artifact.artifact_id} source={table} />
      ))}
      <section>
        <h3 className="mb-2 font-semibold">Corrections applied</h3>
        <CorrectionsList corrections={corrections} />
      </section>
      {/* Printed once under Method and limits, so a printed report does not repeat them. */}
      <section className="print:hidden">
        <h3 className="mb-2 font-semibold">Assumptions</h3>
        <AssumptionsList assumptions={assumptions} />
      </section>
      <p className="hidden text-muted-foreground print:block">
        The assumptions are listed under Method and limits.
      </p>
    </article>
  );
}
