import type { Proposal } from "@/api/generated/model";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { dateAndTime } from "@/lib/format";
import { tableLabel } from "@/lib/labels";

/** The approved fixes applied to the rows behind a number. */
export function CorrectionsList({ corrections }: { corrections: Proposal[] }) {
  if (corrections.length === 0) {
    return (
      <p className="text-muted-foreground">No approved fixes touch the rows behind this number.</p>
    );
  }
  return (
    <Table>
      <TableHead>
        <tr>
          <TableHeaderCell>Record</TableHeaderCell>
          <TableHeaderCell>Table</TableHeaderCell>
          <TableHeaderCell>Field</TableHeaderCell>
          <TableHeaderCell>Old value</TableHeaderCell>
          <TableHeaderCell>New value</TableHeaderCell>
          <TableHeaderCell>Approved by</TableHeaderCell>
        </tr>
      </TableHead>
      <TableBody>
        {corrections.map((fix) => {
          const decision = fix.latest_decision;
          return (
            <TableRow key={fix.proposal_id}>
              <TableCell>{fix.record_key}</TableCell>
              <TableCell>{tableLabel(fix.table)}</TableCell>
              <TableCell>{fix.field}</TableCell>
              <TableCell>{fix.old_value ?? ""}</TableCell>
              <TableCell>{decision?.edited_value ?? fix.new_value ?? ""}</TableCell>
              <TableCell>
                {decision ? `${decision.reviewer}, ${dateAndTime(decision.decided_at)}` : ""}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
