import { ApiError } from "@/api/fetcher";
import { useGetReport, useGetRun, useListResultSets } from "@/api/generated/client";
import { usePersona } from "@/api/persona";
import { useRecipe } from "@/api/recipe";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { TableSkeleton } from "@/components/TableSkeleton";
import { messageOf } from "@/lib/errors";
import { ReportBar } from "./ReportBar";
import { ReportDashboard } from "./ReportDashboard";
import { ReportParagraph } from "./ReportParagraph";
import { ReportStatusLine } from "./ReportStatusLine";
import { Scope2Dashboard } from "./Scope2Dashboard";
import { useLatestDraftRun } from "./useLatestDraftRun";

export function ReportPage({ resultSetId }: { resultSetId: string }) {
  const isSpecialist = usePersona().role === "sustainability_specialist";
  const resultSets = useListResultSets({ recipe_id: useRecipe() });
  const resultSet = resultSets.data?.find((item) => item.result_set_id === resultSetId);
  const run = useGetRun(resultSet?.run_id ?? "", { query: { enabled: resultSet !== undefined } });
  const energy = run.data?.recipe_id === "energy_meter_check";
  const report = useGetReport(resultSetId, { query: { retry: false } });
  const draftRun = useLatestDraftRun(resultSet?.run_id, resultSetId);

  const noDraftYet = report.error instanceof ApiError && report.error.status === 404;
  const drafting = draftRun?.status === "queued" || draftRun?.status === "running";
  // A failed draft hides any older text, so the page never mixes the two.
  const failed =
    draftRun?.status === "failed" && (!report.data || draftRun.created_at > report.data.drafted_at);
  const shown = report.data && !failed ? report.data : undefined;

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-6 py-6 print:max-w-none print:px-0 print:py-0">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">
          {run.data ? (energy ? "Scope 2 report" : "Climate risk report") : "Report"}
        </h1>
        {resultSet ? <ReportStatusLine resultSet={resultSet} report={shown} /> : null}
      </div>

      {resultSets.isPending ? <TableSkeleton rows={6} /> : null}
      {resultSets.isError ? (
        <ErrorState
          title="The results did not load."
          message="Check that the server is running, then try again."
          onRetry={() => void resultSets.refetch()}
        />
      ) : null}
      {resultSets.data && !resultSet ? (
        <EmptyState title="No results match this link. Open the report from the Report tab." />
      ) : null}

      {resultSet ? (
        <ReportBar resultSet={resultSet} hasDraft={shown !== undefined} drafting={drafting} />
      ) : null}

      {drafting ? (
        <div role="status" className="space-y-2">
          <p className="font-medium">Writing a draft. The text appears here when it is done.</p>
          <TableSkeleton rows={6} />
        </div>
      ) : null}
      {failed && draftRun ? (
        <ErrorState
          title="The draft failed."
          message={`${draftRun.error ?? "The text did not pass the checks."} Draft again, or copy the run id for the data specialist.`}
          runId={draftRun.run_id}
        />
      ) : null}

      {report.isPending && resultSet && !drafting ? <TableSkeleton rows={10} /> : null}
      {report.isError && !noDraftYet ? (
        <ErrorState
          title="The report did not load."
          message={messageOf(report.error) ?? "Try again."}
          onRetry={() => void report.refetch()}
        />
      ) : null}
      {noDraftYet && !drafting && !failed ? (
        <EmptyState title="No draft yet.">
          {isSpecialist
            ? "Request a draft to start the review."
            : "The sustainability specialist has not asked for a draft."}
        </EmptyState>
      ) : null}

      {shown && !drafting ? (
        <>
          {run.data ? (
            energy ? (
              <Scope2Dashboard report={shown} />
            ) : (
              <ReportDashboard report={shown} />
            )
          ) : null}
          <article className="mx-auto max-w-column print:max-w-none">
            {shown.paragraphs.map((paragraph, index) => (
              <ReportParagraph
                key={`${paragraph.section}-${paragraph.call_id ?? index}`}
                paragraph={paragraph}
                previousSection={shown.paragraphs[index - 1]?.section}
                metrics={shown.metrics}
                insights={shown.insights}
                suggested={shown.status === "draft" || shown.status === "in_review"}
              />
            ))}
          </article>
        </>
      ) : null}
    </main>
  );
}
