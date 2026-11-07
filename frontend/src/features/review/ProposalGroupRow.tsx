import { ChevronRight } from "lucide-react";
import { TableCell, TableRow } from "@/components/ui/table";
import { BulkDecision } from "@/features/review/BulkDecision";
import type { ProposalGroup } from "@/features/review/proposalGroups";
import { count } from "@/lib/format";
import { proposerLabel, sourceName } from "@/lib/labels";
import { cn } from "@/lib/utils";

interface ProposalGroupRowProps {
  group: ProposalGroup;
  description: string | undefined;
  columns: number;
  collapsed: boolean;
  onToggle: () => void;
  canDecide: boolean;
}

function groupCounts(group: ProposalGroup): string {
  const total = group.proposals.length;
  const fixes = group.proposals.filter((item) => item.action === "fix").length;
  if (fixes === 0) return `${count(total)} ${total === 1 ? "flag" : "flags"}`;
  const noun = total === 1 ? "fix" : "fixes";
  return `${count(total)} ${noun}, ${count(group.openFixIds.length)} open`;
}

/** The heading of one data check in the queue, with its batch decision. */
export function ProposalGroupRow({
  group,
  description,
  columns,
  collapsed,
  onToggle,
  canDecide,
}: ProposalGroupRowProps) {
  return (
    <TableRow className="bg-muted">
      <TableCell colSpan={columns}>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <button
            type="button"
            aria-expanded={!collapsed}
            onClick={onToggle}
            className="flex min-w-0 flex-1 items-start gap-1.5 text-left"
          >
            <ChevronRight
              aria-hidden="true"
              className={cn("mt-0.5 size-4 shrink-0", !collapsed && "rotate-90")}
            />
            <span>
              <span className="font-semibold">{proposerLabel(group.proposer)}</span>
              <span className="ml-3 tabular-nums text-muted-foreground">{groupCounts(group)}</span>
              {description ? (
                <span className="block text-muted-foreground">{description}</span>
              ) : null}
            </span>
          </button>
          {canDecide ? (
            <BulkDecision
              scope={`from ${sourceName(group.proposer)}`}
              openFixIds={group.openFixIds}
            />
          ) : null}
        </div>
      </TableCell>
    </TableRow>
  );
}
