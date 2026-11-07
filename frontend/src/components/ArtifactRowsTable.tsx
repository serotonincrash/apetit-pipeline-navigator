import { useState } from "react";
import { useListArtifactRows } from "@/api/generated/client";
import { ErrorState } from "@/components/ErrorState";
import { ExportLink } from "@/components/ExportLink";
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
import { cell, count } from "@/lib/format";
import { columnLabel } from "@/lib/labels";

const PAGE = 15;

interface ArtifactRowsTableProps {
  artifactId: string;
  filters?: string[];
  /** Rows the filter selects, when the caller already knows it. */
  knownTotal?: number;
}

/** Rows of one table in pages, with the Excel export for the same filter. */
export function ArtifactRowsTable({ artifactId, filters, knownTotal }: ArtifactRowsTableProps) {
  const [offset, setOffset] = useState(0);
  const rows = useListArtifactRows(artifactId, {
    filter: filters?.length ? filters : undefined,
    limit: PAGE,
    offset,
  });
  const total = rows.data?.total ?? knownTotal ?? 0;

  return (
    <div>
      <div className="flex items-center gap-4">
        <ExportLink artifactId={artifactId} filters={filters} />
        <span className="text-muted-foreground">
          {total > 0
            ? `Rows ${count(offset + 1)} to ${count(Math.min(offset + PAGE, total))} of ${count(total)}`
            : ""}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <Button size="sm" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>
            Previous rows
          </Button>
          <Button
            size="sm"
            disabled={offset + PAGE >= total}
            onClick={() => setOffset(offset + PAGE)}
          >
            Next rows
          </Button>
        </span>
      </div>
      <div className="mt-2 overflow-x-auto border">
        {rows.isPending ? <TableSkeleton rows={5} /> : null}
        {rows.isError ? (
          <ErrorState
            title="The rows did not load."
            message="Try again, or export the rows to Excel."
            onRetry={() => void rows.refetch()}
          />
        ) : null}
        {rows.data ? (
          <Table>
            <TableHead>
              <tr>
                {rows.data.columns.map((column) => (
                  <TableHeaderCell key={column} className="whitespace-nowrap">
                    {columnLabel(column)}
                  </TableHeaderCell>
                ))}
              </tr>
            </TableHead>
            <TableBody>
              {rows.data.rows.map((row, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: table rows have no id of their own
                <TableRow key={offset + index}>
                  {rows.data.columns.map((column) => (
                    <TableCell key={column} className="whitespace-nowrap">
                      {cell(row[column])}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </div>
    </div>
  );
}
