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
import { recipeLabel } from "@/lib/recipes";

/** Runs of a recipe, from the raw package to results, including what-if runs. */
export function RecipeRunsTable({ runs }: { runs: Run[] }) {
  return (
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
            <TableCell>{recipeLabel(run)}</TableCell>
            <TableCell>{startedText(run)}</TableCell>
            <TableCell>{run.triggered_by}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
