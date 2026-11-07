import type { Assumption } from "@/api/generated/model";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { assumptionValue } from "@/lib/assumptions";

/** Assumptions with their label, value, unit and source. */
export function AssumptionsList({ assumptions }: { assumptions: Assumption[] }) {
  if (assumptions.length === 0) {
    return <p className="text-muted-foreground">No assumptions are recorded for this number.</p>;
  }
  return (
    <Table>
      <TableHead>
        <tr>
          <TableHeaderCell>Assumption</TableHeaderCell>
          <TableHeaderCell numeric>Value</TableHeaderCell>
          <TableHeaderCell>Unit</TableHeaderCell>
          <TableHeaderCell>Source</TableHeaderCell>
        </tr>
      </TableHead>
      <TableBody>
        {assumptions.map((assumption) => (
          <TableRow key={assumption.assumption_id}>
            <TableCell>{assumption.label}</TableCell>
            <TableCell numeric>{assumptionValue(assumption.value)}</TableCell>
            <TableCell>{assumption.unit}</TableCell>
            <TableCell className="text-muted-foreground">{assumption.source}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
