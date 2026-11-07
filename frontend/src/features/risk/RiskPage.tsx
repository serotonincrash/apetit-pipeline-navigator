import { useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { useListMetrics, useListResultSets } from "@/api/generated/client";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { useSources } from "@/components/SourcesContext";
import { TableSkeleton } from "@/components/TableSkeleton";
import { Button } from "@/components/ui/button";
import { AssumptionsPanel } from "@/features/risk/AssumptionsPanel";
import { BreakdownTable } from "@/features/risk/BreakdownTable";
import { HeadlineTiles } from "@/features/risk/HeadlineTiles";
import { MeasureSwitch } from "@/features/risk/MeasureSwitch";
import { RiskChart } from "@/features/risk/RiskChart";
import { RiskFilters } from "@/features/risk/RiskFilters";
import {
  BAD_YEAR_METRIC,
  badYearByRow,
  buildRows,
  MEASURES,
  type Measure,
  totals,
  transitionChoice,
} from "@/lib/risk";

export interface RiskSearch {
  set?: string;
  crop?: string;
  region?: string;
  measure?: Measure;
  ssp126?: string;
  ssp245?: string;
  ssp585?: string;
  panel?: "assumptions";
  sources?: string;
}

export function RiskPage({ search }: { search: RiskSearch }) {
  const navigate = useNavigate({ from: "/risk" });
  const { openSources } = useSources();
  const resultSets = useListResultSets();
  const ordered = useMemo(
    () => [...(resultSets.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [resultSets.data],
  );
  const resultSetId = search.set ?? ordered[0]?.result_set_id ?? "";
  const measure = search.measure ?? "cost";
  const metricName = MEASURES.find((item) => item.id === measure)?.metric ?? MEASURES[0]?.metric;
  const enabled = resultSetId !== "";
  const measureMetrics = useListMetrics(
    resultSetId,
    { name: metricName, limit: 5000 },
    { query: { enabled } },
  );
  const badYears = useListMetrics(
    resultSetId,
    { name: BAD_YEAR_METRIC, limit: 5000 },
    { query: { enabled } },
  );

  const choice = transitionChoice(search);
  const setSearch = (next: RiskSearch) => void navigate({ search: next, replace: true });
  const rows = useMemo(
    () => buildRows(measureMetrics.data?.items ?? [], choice, search),
    [measureMetrics.data, choice, search],
  );
  const headline = useMemo(
    () => totals(measureMetrics.data?.items ?? [], choice),
    [measureMetrics.data, choice],
  );
  const badByRow = useMemo(() => badYearByRow(badYears.data?.items ?? []), [badYears.data]);

  return (
    <main className="space-y-5 px-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Risk view</h1>
        <div className="flex items-center gap-3">
          <MeasureSwitch
            value={measure}
            onChange={(next) => setSearch({ ...search, measure: next })}
          />
          {enabled ? (
            <Button onClick={() => setSearch({ ...search, panel: "assumptions" })}>
              Assumptions
            </Button>
          ) : null}
        </div>
      </div>

      {resultSets.isPending ? <TableSkeleton rows={10} /> : null}
      {resultSets.isError ? (
        <ErrorState
          title="The results did not load."
          message="Check that the server is running, then try again."
          onRetry={() => void resultSets.refetch()}
        />
      ) : null}
      {resultSets.data && ordered.length === 0 ? (
        <EmptyState title="No results yet. Review the fixes and run again." />
      ) : null}

      {enabled ? (
        <>
          <RiskFilters
            resultSets={ordered}
            resultSetId={resultSetId}
            crop={search.crop}
            region={search.region}
            choice={choice}
            onResultSet={(id) => setSearch({ ...search, set: id })}
            onCrop={(crop) => setSearch({ ...search, crop })}
            onRegion={(region) => setSearch({ ...search, region })}
            onTransition={(scenario, ngfs) => setSearch({ ...search, [scenario]: ngfs })}
          />
          {measureMetrics.isPending ? <TableSkeleton rows={10} /> : null}
          {measureMetrics.isError ? (
            <ErrorState
              title="The numbers did not load."
              message="Try again, or pick other results."
              onRetry={() => void measureMetrics.refetch()}
            />
          ) : null}
          {measureMetrics.data ? (
            <>
              <HeadlineTiles totals={headline} />
              {rows.length === 0 ? (
                <EmptyState title="No numbers match these filters.">
                  Clear the crop or region to see more.
                </EmptyState>
              ) : (
                <>
                  <RiskChart rows={rows} onOpenSources={openSources} />
                  <BreakdownTable rows={rows} badYears={badByRow} />
                </>
              )}
            </>
          ) : null}
        </>
      ) : null}

      {search.panel === "assumptions" && enabled ? (
        <AssumptionsPanel
          resultSetId={resultSetId}
          onClose={() => setSearch({ ...search, panel: undefined })}
        />
      ) : null}
    </main>
  );
}
