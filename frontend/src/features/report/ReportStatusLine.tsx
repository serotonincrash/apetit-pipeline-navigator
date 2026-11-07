import type { Report, ResultSet } from "@/api/generated/model";
import { StatusLabel } from "@/components/StatusLabel";
import { dateAndTime } from "@/lib/format";

/** The state of the results and who moved them there, with absolute dates. It prints. */
export function ReportStatusLine({
  resultSet,
  report,
}: {
  resultSet: ResultSet;
  report: Report | undefined;
}) {
  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-muted-foreground">
      <StatusLabel status={resultSet.status} />
      {report ? (
        <span>
          Draft {report.version}, written {dateAndTime(report.drafted_at)}
        </span>
      ) : null}
      {resultSet.approved_by ? <span>Approved by {resultSet.approved_by}</span> : null}
      {resultSet.published_at ? <span>Published {dateAndTime(resultSet.published_at)}</span> : null}
    </p>
  );
}
