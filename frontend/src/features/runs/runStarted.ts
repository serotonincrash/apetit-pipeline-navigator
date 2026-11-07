import type { Run } from "@/api/generated/model";
import { dateAndTime, relativeTime } from "@/lib/format";

/** When a run started: relative while it runs, an absolute date once it is done. */
export function startedText(run: Run): string {
  const started = run.started_at ?? run.created_at;
  if (run.status === "running" || run.status === "queued") {
    return run.started_at ? `Started ${relativeTime(started)}` : "Waiting to start";
  }
  return dateAndTime(started);
}
