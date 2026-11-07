import { Link } from "@tanstack/react-router";
import type { Run } from "@/api/generated/model";
import { StatusLabel } from "@/components/StatusLabel";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { startedText } from "@/features/runs/runStarted";

/** Runs that only write report text for the results of an earlier run. */
export function ReportDraftsTable({ runs }: { runs: Run[] }) {
  return (
    <Table>
      <TableHead>
        <tr>
          <TableHeaderCell>Draft</TableHeaderCell>
          <TableHeaderCell>Status</TableHeaderCell>
          <TableHeaderCell>Results of run</TableHeaderCell>
          <TableHeaderCell>Started</TableHeaderCell>
          <TableHeaderCell>Requested by</TableHeaderCell>
        </tr>
      </TableHead>
      <TableBody>
        {runs.map((run) => (
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
            <TableCell>
              {run.parent_run_id ? (
                <Link
                  to="/runs/$runId"
                  params={{ runId: run.parent_run_id }}
                  className="text-primary underline"
                >
                  {run.parent_run_id}
                </Link>
              ) : null}
            </TableCell>
            <TableCell>{startedText(run)}</TableCell>
            <TableCell>{run.triggered_by}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
