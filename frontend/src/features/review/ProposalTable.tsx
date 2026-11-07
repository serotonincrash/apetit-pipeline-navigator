import { useEffect, useRef } from "react";
import type { Proposal } from "@/api/generated/model";
import { StatusLabel } from "@/components/StatusLabel";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { tableLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

interface ProposalTableProps {
  proposals: Proposal[];
  selectedId: string | undefined;
  onSelect: (proposalId: string) => void;
}

export function ProposalTable({ proposals, selectedId, onSelect }: ProposalTableProps) {
  const selectedRow = useRef<HTMLTableRowElement>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll only when the selection moves
  useEffect(() => {
    selectedRow.current?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <Table>
      <TableHead className="sticky top-0">
        <tr>
          <TableHeaderCell>Data check</TableHeaderCell>
          <TableHeaderCell>Table</TableHeaderCell>
          <TableHeaderCell>Record</TableHeaderCell>
          <TableHeaderCell>Field</TableHeaderCell>
          <TableHeaderCell numeric>Old value</TableHeaderCell>
          <TableHeaderCell numeric>New value</TableHeaderCell>
          <TableHeaderCell>Status</TableHeaderCell>
        </tr>
      </TableHead>
      <TableBody>
        {proposals.map((proposal) => {
          const selected = proposal.proposal_id === selectedId;
          return (
            <TableRow
              key={proposal.proposal_id}
              ref={selected ? selectedRow : undefined}
              onClick={() => onSelect(proposal.proposal_id)}
              aria-selected={selected}
              className={cn("cursor-pointer hover:bg-muted", selected && "bg-selected")}
            >
              <TableCell>{proposal.rule_id}</TableCell>
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
      </TableBody>
    </Table>
  );
}
