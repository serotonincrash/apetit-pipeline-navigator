import { Fragment, useEffect, useRef } from "react";
import type { Rule } from "@/api/generated/model";
import { StatusLabel } from "@/components/StatusLabel";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { ProposalGroupRow } from "@/features/review/ProposalGroupRow";
import type { ProposalGroup } from "@/features/review/proposalGroups";
import { tableLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

interface ProposalTableProps {
  groups: ProposalGroup[];
  rules: Rule[];
  collapsed: ReadonlySet<string>;
  onToggle: (ruleId: string) => void;
  canDecide: boolean;
  selectedId: string | undefined;
  onSelect: (proposalId: string) => void;
}

const COLUMNS = 6;

export function ProposalTable({
  groups,
  rules,
  collapsed,
  onToggle,
  canDecide,
  selectedId,
  onSelect,
}: ProposalTableProps) {
  const selectedRow = useRef<HTMLTableRowElement>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll only when the selection moves
  useEffect(() => {
    selectedRow.current?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <Table>
      <TableHead className="sticky top-0">
        <tr>
          <TableHeaderCell>Table</TableHeaderCell>
          <TableHeaderCell>Record</TableHeaderCell>
          <TableHeaderCell>Field</TableHeaderCell>
          <TableHeaderCell numeric>Old value</TableHeaderCell>
          <TableHeaderCell numeric>New value</TableHeaderCell>
          <TableHeaderCell>Status</TableHeaderCell>
        </tr>
      </TableHead>
      <TableBody>
        {groups.map((group) => {
          const isCollapsed = collapsed.has(group.ruleId);
          return (
            <Fragment key={group.ruleId}>
              <ProposalGroupRow
                group={group}
                description={rules.find((rule) => rule.rule_id === group.ruleId)?.description}
                columns={COLUMNS}
                collapsed={isCollapsed}
                onToggle={() => onToggle(group.ruleId)}
                canDecide={canDecide}
              />
              {isCollapsed
                ? null
                : group.proposals.map((proposal) => {
                    const selected = proposal.proposal_id === selectedId;
                    return (
                      <TableRow
                        key={proposal.proposal_id}
                        ref={selected ? selectedRow : undefined}
                        onClick={() => onSelect(proposal.proposal_id)}
                        aria-selected={selected}
                        className={cn("cursor-pointer hover:bg-muted", selected && "bg-selected")}
                      >
                        <TableCell>{tableLabel(proposal.table)}</TableCell>
                        <TableCell>{proposal.record_key}</TableCell>
                        <TableCell>{proposal.field}</TableCell>
                        <TableCell numeric>{proposal.old_value ?? ""}</TableCell>
                        <TableCell numeric>
                          {proposal.latest_decision?.edited_value ?? proposal.new_value ?? ""}
                        </TableCell>
                        <TableCell>
                          <StatusLabel status={proposal.status} />
                        </TableCell>
                      </TableRow>
                    );
                  })}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
}
