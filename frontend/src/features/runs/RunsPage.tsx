import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { getListRunsQueryKey, useCreateRun, useListRuns } from "@/api/generated/client";
import type { Run } from "@/api/generated/model";
import { requireName } from "@/api/persona";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { StatusLabel } from "@/components/StatusLabel";
import { TableSkeleton } from "@/components/TableSkeleton";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { messageOf } from "@/lib/errors";
import { dateAndTime, relativeTime } from "@/lib/format";
import { recipeLabel } from "@/lib/recipes";

function startedText(run: Run): string {
  const started = run.started_at ?? run.created_at;
  if (run.status === "running" || run.status === "queued") {
    return run.started_at ? `Started ${relativeTime(started)}` : "Waiting to start";
  }
  return dateAndTime(started);
}

export function RunsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const runs = useListRuns(
    { limit: 100 },
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
                  data: { recipe_id: "farm_climate_risk", run_fix_proposer: fixProposer },
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
        <EmptyState title="No runs yet.">Start a run to check the farm data.</EmptyState>
      ) : null}
      {runs.data && runs.data.items.length > 0 ? (
        <Table>
          <TableHead>
            <tr>
              <TableHeaderCell>Run</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>Recipe</TableHeaderCell>
              <TableHeaderCell>Started</TableHeaderCell>
              <TableHeaderCell>Started by</TableHeaderCell>
            </tr>
          </TableHead>
          <TableBody>
            {runs.data.items.map((run) => (
              <TableRow key={run.run_id}>
                <TableCell>
                  <Link
                    to="/runs/$runId"
                    params={{ runId: run.run_id }}
                    className="text-primary underline"
                  >
                    {run.run_id}
                  </Link>
                </TableCell>
                <TableCell>
                  <StatusLabel status={run.status} />
                </TableCell>
                <TableCell>{recipeLabel(run)}</TableCell>
                <TableCell>{startedText(run)}</TableCell>
                <TableCell>{run.triggered_by}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </main>
  );
}
