import { Link } from "@tanstack/react-router";
import type { RunDetail } from "@/api/generated/model";

/** What a report run did. It drafts text for existing results, so it has no steps to show. */
export function ReportRunSummary({ run }: { run: RunDetail }) {
  const resultSetId = run.params.result_set_id;
  const link =
    typeof resultSetId === "string" ? (
      <Link to="/report/$resultSetId" params={{ resultSetId }} className="text-primary underline">
        {run.status === "failed" ? "Draft again on the report" : "Open the report"}
      </Link>
    ) : null;
  return (
    <div className="max-w-column space-y-2">
      <p>
        {run.status === "succeeded"
          ? "Drafted the report text for these results. A reviewer checks it on the report."
          : run.status === "failed"
            ? "The draft was not stored, so the report keeps its earlier text."
            : "Writing the report text. It appears on the report when every paragraph has passed its checks."}
      </p>
      {link}
    </div>
  );
}
