import { useListArtifactRows } from "@/api/generated/client";
import { ErrorState } from "@/components/ErrorState";
import { TableSkeleton } from "@/components/TableSkeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";

/** Actions the comparison step could not price, with its reason. */
export function RefusedActions({ artifactId }: { artifactId: string }) {
  const rows = useListArtifactRows(artifactId, { limit: 100 });
  if (rows.isPending) return <TableSkeleton rows={2} />;
  if (rows.isError) {
    return (
      <ErrorState
        title="The refused actions did not load."
        message="Try again."
        onRetry={() => void rows.refetch()}
      />
    );
  }
  return (
    <Table>
      <TableHead>
        <tr>
          <TableHeaderCell>Action</TableHeaderCell>
          <TableHeaderCell>Why it was not priced</TableHeaderCell>
        </tr>
      </TableHead>
      <TableBody>
        {rows.data.rows.map((row) => (
          <TableRow key={String(row.action_id)}>
            <TableCell>{String(row.name)}</TableCell>
            <TableCell>{String(row.why_not)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
