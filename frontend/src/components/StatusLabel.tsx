import { statusLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

const COLOURS: Record<string, string> = {
  queued: "text-status-queued",
  pending: "text-status-queued",
  reused: "text-status-queued",
  running: "text-status-running",
  succeeded: "text-status-succeeded",
  failed: "text-status-failed",
  open: "text-status-open",
  approved: "text-status-approved",
  rejected: "text-status-rejected",
  flag: "text-status-flag",
  draft: "text-status-queued",
  in_review: "text-status-running",
  published: "text-status-succeeded",
  superseded: "text-status-queued",
};

export const statusColour = (status: string) => COLOURS[status];

export function StatusLabel({ status }: { status: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 font-medium", statusColour(status))}>
      <span aria-hidden="true" className="size-2 rounded-full bg-current" />
      {statusLabel(status)}
    </span>
  );
}
