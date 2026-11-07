import { Navigate } from "@tanstack/react-router";
import { useListResultSets } from "@/api/generated/client";
import { useRecipe } from "@/api/recipe";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { TableSkeleton } from "@/components/TableSkeleton";

/** The Report tab: sends the person to the report of the newest results. */
export function ReportRedirect() {
  const resultSets = useListResultSets({ recipe_id: useRecipe() });
  const newest = [...(resultSets.data ?? [])].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  )[0];
  if (newest) {
    return (
      <Navigate to="/report/$resultSetId" params={{ resultSetId: newest.result_set_id }} replace />
    );
  }
  return (
    <main className="mx-auto max-w-5xl space-y-5 px-6 py-6">
      <h1 className="text-lg font-semibold">Report</h1>
      {resultSets.isPending ? <TableSkeleton rows={6} /> : null}
      {resultSets.isError ? (
        <ErrorState
          title="The results did not load."
          message="Check that the server is running, then try again."
          onRetry={() => void resultSets.refetch()}
        />
      ) : null}
      {resultSets.data ? (
        <EmptyState title="No results yet. Review the fixes and run again." />
      ) : null}
    </main>
  );
}
