import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { getListRunsQueryKey, useCreateRun, useListRuns } from "@/api/generated/client";
import { requireName } from "@/api/persona";
import { useRecipe } from "@/api/recipe";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { TableSkeleton } from "@/components/TableSkeleton";
import { Button } from "@/components/ui/button";
import { RecipeRunsTable } from "@/features/runs/RecipeRunsTable";
import { ReportDraftsTable } from "@/features/runs/ReportDraftsTable";
import { messageOf } from "@/lib/errors";
import { checkedData } from "@/lib/recipes";

export function RunsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const recipe = useRecipe();
  const runs = useListRuns(
    { limit: 100, recipe_id: recipe },
    {
      query: {
        refetchInterval: (query) =>
          query.state.data?.items.some((run) => run.status === "queued" || run.status === "running")
            ? 3000
            : false,
      },
    },
  );
  const [fixProposer, setFixProposer] = useState(false);
  const recipeRuns = runs.data?.items.filter((run) => run.kind !== "report") ?? [];
  const reportDrafts = runs.data?.items.filter((run) => run.kind === "report") ?? [];
  const start = useCreateRun({
    mutation: {
      onSuccess: (run) => {
        void queryClient.invalidateQueries({ queryKey: getListRunsQueryKey() });
        void navigate({ to: "/runs/$runId", params: { runId: run.run_id } });
      },
    },
  });

  return (
    <main className="mx-auto max-w-5xl px-6 py-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Runs</h1>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={fixProposer}
              onChange={(event) => setFixProposer(event.target.checked)}
            />
            Also look for problems the data checks miss
          </label>
          <Button
            variant="primary"
            disabled={start.isPending}
            onClick={() => {
              if (requireName()) {
                start.mutate({
                  data: { recipe_id: recipe, run_fix_proposer: fixProposer },
                });
              }
            }}
          >
            Start a run
          </Button>
        </div>
      </div>
      {start.isError ? (
        <ErrorState title="The run did not start." message={messageOf(start.error)} />
      ) : null}
      {runs.isPending ? <TableSkeleton /> : null}
      {runs.isError ? (
        <ErrorState
          title="The runs did not load."
          message="Check that the server is running, then try again."
          onRetry={() => void runs.refetch()}
        />
      ) : null}
      {runs.data && runs.data.items.length === 0 ? (
        <EmptyState title="No runs yet.">
          Start a run to check the {checkedData(recipe)}.
        </EmptyState>
      ) : null}
      {runs.data && runs.data.items.length > 0 ? (
        <>
          {recipeRuns.length > 0 ? <RecipeRunsTable runs={recipeRuns} /> : null}
          <h2 className="mb-2 mt-8 font-semibold">Report drafts</h2>
          {reportDrafts.length > 0 ? (
            <ReportDraftsTable runs={reportDrafts} />
          ) : (
            <p className="text-muted-foreground">
              No drafts yet. Request one on the report once a run has results.
            </p>
          )}
        </>
      ) : null}
    </main>
  );
}
