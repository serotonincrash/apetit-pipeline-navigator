import { useNavigate } from "@tanstack/react-router";
import { useCreateRun } from "@/api/generated/client";
import { requireName } from "@/api/persona";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { messageOf } from "@/lib/errors";

/** Shown once decisions are in that the latest run has not used. */
export function RunAgainBar({ decisions }: { decisions: number }) {
  const navigate = useNavigate();
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
          if (requireName()) start.mutate({ data: { recipe_id: "farm_climate_risk" } });
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
