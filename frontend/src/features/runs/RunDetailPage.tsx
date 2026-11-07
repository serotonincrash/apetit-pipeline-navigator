import { Link } from "@tanstack/react-router";
import { useGetRun } from "@/api/generated/client";
import { ErrorState } from "@/components/ErrorState";
import { StatusLabel } from "@/components/StatusLabel";
import { TableSkeleton } from "@/components/TableSkeleton";
import { ReportRunSummary } from "@/features/runs/ReportRunSummary";
import { StepItem } from "@/features/runs/StepItem";
import { useRunEvents } from "@/features/runs/useRunEvents";
import { runErrorText } from "@/lib/errors";
import { dateAndTime, relativeTime } from "@/lib/format";
import { recipeLabel } from "@/lib/recipes";

export function RunDetailPage({ runId }: { runId: string }) {
  const run = useGetRun(runId);
  const sections = useRunEvents(runId);
  const active = run.data?.status === "queued" || run.data?.status === "running";

  return (
    <main className="mx-auto max-w-5xl px-6 py-6">
      <Link to="/runs" className="text-primary underline">
        All runs
      </Link>
      {run.isPending ? <TableSkeleton rows={10} /> : null}
      {run.isError ? (
        <ErrorState
          title="This run did not load."
          message="Check the run id in the address, or go back to all runs."
          runId={runId}
          onRetry={() => void run.refetch()}
        />
      ) : null}
      {run.data ? (
        <>
          <div className="mb-5 mt-3">
            <h1 className="text-lg font-semibold">
              {recipeLabel(run.data)}, {run.data.run_id}
            </h1>
            <p className="mt-1 flex items-center gap-3 text-muted-foreground">
              <StatusLabel status={run.data.status} />
              <span>
                {active && run.data.started_at
                  ? `Started ${relativeTime(run.data.started_at)}`
                  : `Created ${dateAndTime(run.data.created_at)}`}
              </span>
              <span>by {run.data.triggered_by}</span>
            </p>
            {run.data.status === "failed" &&
            run.data.error &&
            !run.data.steps.some((s) => s.error) ? (
              <div className="mt-2">
                <ErrorState
                  title="The run failed."
                  message={runErrorText(run.data.error)}
                  runId={run.data.run_id}
                />
              </div>
            ) : null}
          </div>
          {run.data.kind === "report" ? <ReportRunSummary run={run.data} /> : null}
          <ol>
            {[...run.data.steps]
              .sort((a, b) => a.position - b.position)
              .map((step) => (
                <StepItem
                  key={step.step_run_id}
                  runId={run.data.run_id}
                  step={step}
                  tables={run.data.artifacts.filter((a) => a.step_run_id === step.step_run_id)}
                  sections={sections[step.step] ?? []}
                />
              ))}
          </ol>
        </>
      ) : null}
    </main>
  );
}
