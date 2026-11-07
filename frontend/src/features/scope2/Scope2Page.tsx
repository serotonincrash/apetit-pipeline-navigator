import { useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { useListResultSets } from "@/api/generated/client";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ResultSetSelect } from "@/components/ResultSetSelect";
import { TableSkeleton } from "@/components/TableSkeleton";
import { InventoryDifferenceTable } from "@/features/scope2/InventoryDifferenceTable";
import { Scope2Table } from "@/features/scope2/Scope2Table";
import { useScope2Metrics } from "@/features/scope2/useScope2Metrics";

export interface Scope2Search {
  set?: string;
}

export function Scope2Page({ search }: { search: Scope2Search }) {
  const navigate = useNavigate({ from: "/scope2" });
  const resultSets = useListResultSets({ recipe_id: "energy_meter_check" });
  const ordered = useMemo(
    () => [...(resultSets.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [resultSets.data],
  );
  const resultSet = ordered.find((item) => item.result_set_id === search.set) ?? ordered[0];
  const resultSetId = resultSet?.result_set_id ?? "";
  const metrics = useScope2Metrics(resultSetId);
  const empty = metrics.use.length === 0 && metrics.location.length === 0;

  return (
    <main className="space-y-5 px-6 py-6">
      <h1 className="text-lg font-semibold">Scope 2</h1>

      {resultSets.isPending ? <TableSkeleton rows={6} /> : null}
      {resultSets.isError ? (
        <ErrorState
          title="The results did not load."
          message="Check that the server is running, then try again."
          onRetry={() => void resultSets.refetch()}
        />
      ) : null}
      {resultSets.data && ordered.length === 0 ? (
        <EmptyState title="No Scope 2 results yet. Review the fixes and run again." />
      ) : null}

      {resultSet ? (
        <>
          <ResultSetSelect
            resultSets={ordered}
            resultSetId={resultSetId}
            onChange={(id) => void navigate({ search: { ...search, set: id }, replace: true })}
          />
          {metrics.isPending ? <TableSkeleton rows={10} /> : null}
          {metrics.isError ? (
            <ErrorState
              title="The Scope 2 figures did not load."
              message="Try again, or pick other results."
              runId={resultSet.run_id}
              onRetry={metrics.refetch}
            />
          ) : null}
          {!metrics.isPending && !metrics.isError && empty ? (
            <EmptyState title="These results have no Scope 2 figures.">
              Pick other results, or run the check again.
            </EmptyState>
          ) : null}
          {!metrics.isPending && !metrics.isError && !empty ? (
            <>
              <section className="space-y-2">
                <h2 className="font-semibold">Electricity and Scope 2 by site and year</h2>
                <div className="max-w-5xl overflow-x-auto border">
                  <Scope2Table
                    use={metrics.use}
                    location={metrics.location}
                    market={metrics.market}
                  />
                </div>
              </section>
              {metrics.locationDifference.length + metrics.marketDifference.length > 0 ? (
                <section className="space-y-2">
                  <h2 className="font-semibold">Difference from the answer inventories</h2>
                  <p className="text-muted-foreground">
                    Calculated Scope 2 minus the inventory figure. A negative number means the
                    calculation is below the inventory.
                  </p>
                  <div className="max-w-5xl overflow-x-auto border">
                    <InventoryDifferenceTable
                      location={metrics.locationDifference}
                      market={metrics.marketDifference}
                    />
                  </div>
                </section>
              ) : null}
            </>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
