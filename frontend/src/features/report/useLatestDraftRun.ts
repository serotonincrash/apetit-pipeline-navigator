import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { getGetReportQueryKey, useListRuns } from "@/api/generated/client";
import type { Run } from "@/api/generated/model";

const ACTIVE = new Set(["queued", "running"]);

/** The newest report run for an analysis run. It refreshes the report when the run succeeds. */
export function useLatestDraftRun(analysisRunId: string | undefined, resultSetId: string) {
  const queryClient = useQueryClient();
  const runs = useListRuns(
    { limit: 100 },
    {
      query: {
        refetchInterval: (query) =>
          query.state.data?.items.some((run) => ACTIVE.has(run.status)) ? 2000 : false,
      },
    },
  );
  const latest: Run | undefined = runs.data?.items
    .filter((run) => run.kind === "report" && run.parent_run_id === analysisRunId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const status = latest?.status;
  useEffect(() => {
    if (status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: getGetReportQueryKey(resultSetId) });
    }
  }, [status, queryClient, resultSetId]);
  return latest;
}
