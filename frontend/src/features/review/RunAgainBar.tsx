import { useNavigate } from "@tanstack/react-router";
import { useCreateRun, useGetRun } from "@/api/generated/client";
import { requireName } from "@/api/persona";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { messageOf } from "@/lib/errors";

/** Shown once decisions are in that the latest run has not used. */
export function RunAgainBar({ decisions, runId }: { decisions: number; runId: string }) {
  const navigate = useNavigate();
  const run = useGetRun(runId);
  // The next run keeps the option, so proposals the assistant suggested stay in the queue.
  const stepParams = run.data?.params.step_params as
    | { propose_fixes?: { enabled?: boolean } }
    | undefined;
  const fixProposer = stepParams?.propose_fixes?.enabled === true;
  const start = useCreateRun({
    mutation: {
      onSuccess: (run) => void navigate({ to: "/runs/$runId", params: { runId: run.run_id } }),
    },
  });
  return (
    <div className="flex items-center gap-4 border bg-selected px-3 py-2">
      <p className="flex-1">
        {decisions} new {decisions === 1 ? "decision is" : "decisions are"} in. The next run applies
        them.
      </p>
      <Button
        variant="primary"
        disabled={start.isPending}
        onClick={() => {
          if (requireName()) {
            start.mutate({
              data: { recipe_id: "farm_climate_risk", run_fix_proposer: fixProposer },
            });
          }
        }}
      >
        Run again with approved fixes
      </Button>
      {start.isError ? (
        <ErrorState title="The run did not start." message={messageOf(start.error)} />
      ) : null}
    </div>
  );
}
