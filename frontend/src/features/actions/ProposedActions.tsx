import { useListActions } from "@/api/generated/client";
import { ErrorState } from "@/components/ErrorState";
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
import { useActionDecision } from "@/features/actions/useActionDecisions";
import { messageOf } from "@/lib/errors";

function costSource(cost: Record<string, unknown>): string {
  return typeof cost.source === "string" ? cost.source : "";
}

/** Actions waiting for a decision on whether to run them. */
export function ProposedActions({ canDecide }: { canDecide: boolean }) {
  const proposed = useListActions({ status: "proposed" });
  const decision = useActionDecision();

  if (proposed.isPending) return <TableSkeleton rows={3} />;
  if (proposed.isError) {
    return (
      <ErrorState
        title="The proposed actions did not load."
        message="Check that the server is running, then try again."
        onRetry={() => void proposed.refetch()}
      />
    );
  }
  if (proposed.data.length === 0) {
    return (
      <p className="text-muted-foreground">
        No proposed actions are waiting. New ones appear here after a run suggests them.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {decision.error ? (
        <ErrorState title="The decision was not saved." message={messageOf(decision.error)} />
      ) : null}
      <Table>
        <TableHead>
          <tr>
            <TableHeaderCell>Action</TableHeaderCell>
            <TableHeaderCell>Driver</TableHeaderCell>
            <TableHeaderCell>Cost and its source</TableHeaderCell>
            <TableHeaderCell>Confidence</TableHeaderCell>
            {canDecide ? <TableHeaderCell>Decision</TableHeaderCell> : null}
          </tr>
        </TableHead>
        <TableBody>
          {proposed.data.map((action) => (
            <TableRow key={action.action_id}>
              <TableCell>{action.short_name ?? action.name}</TableCell>
              <TableCell>{action.driver}</TableCell>
              <TableCell>{costSource(action.cost)}</TableCell>
              <TableCell>{action.confidence}</TableCell>
              {canDecide ? (
                <TableCell>
                  <span className="flex gap-2">
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={decision.isPending}
                      onClick={() => decision.decide(action.action_id, "approve")}
                    >
                      Approve to run
                    </Button>
                    <Button
                      size="sm"
                      disabled={decision.isPending}
                      onClick={() => decision.decide(action.action_id, "reject")}
                    >
                      Reject action
                    </Button>
                  </span>
                </TableCell>
              ) : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
