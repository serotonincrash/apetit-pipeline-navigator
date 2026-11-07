import { useState } from "react";
import type { Action, ActionOption, Assumption, Metric } from "@/api/generated/model";
import { InfoTip } from "@/components/InfoTip";
import { Table, TableBody, TableHead, TableHeaderCell } from "@/components/ui/table";
import { ActionOptionRow, type OptionMetrics } from "@/features/actions/ActionOptionRow";

interface ActionOptionsTableProps {
  options: ActionOption[];
  actions: Action[];
  assumptions: Assumption[];
  riskRemoved: Metric[];
  emissionsRemoved: Metric[];
  resultSetId: string;
  canDecide: boolean;
}

const COLUMNS = 7;

function forAction(metrics: Metric[], actionId: string): Metric | undefined {
  return metrics.find((metric) => metric.action_id === actionId);
}

export function ActionOptionsTable(props: ActionOptionsTableProps) {
  const [openId, setOpenId] = useState<string>();
  const maxRiskRemoved = Math.max(0, ...props.riskRemoved.map((metric) => metric.value));
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHead>
          <tr>
            <TableHeaderCell>Action</TableHeaderCell>
            <TableHeaderCell numeric>Cost, € per year</TableHeaderCell>
            <TableHeaderCell numeric>
              Risk removed, € per year
              <InfoTip term="risk removed">
                This is also the break-even cost. The action pays for itself when it costs less than
                this each year.
              </InfoTip>
            </TableHeaderCell>
            <TableHeaderCell>
              <span className="sr-only">Risk removed, compared across actions</span>
            </TableHeaderCell>
            <TableHeaderCell numeric>Emissions removed, t CO2e per year</TableHeaderCell>
            <TableHeaderCell>Mark</TableHeaderCell>
            <TableHeaderCell>
              <span className="sr-only">Details</span>
            </TableHeaderCell>
          </tr>
        </TableHead>
        <TableBody>
          {props.options.map((option) => {
            const metrics: OptionMetrics = {
              riskRemoved: forAction(props.riskRemoved, option.action_id),
              emissionsRemoved: forAction(props.emissionsRemoved, option.action_id),
            };
            return (
              <ActionOptionRow
                key={option.option_id}
                option={option}
                action={props.actions.find((action) => action.action_id === option.action_id)}
                metrics={metrics}
                assumptions={props.assumptions}
                maxRiskRemoved={maxRiskRemoved}
                resultSetId={props.resultSetId}
                canDecide={props.canDecide}
                open={openId === option.option_id}
                onToggle={() =>
                  setOpenId(openId === option.option_id ? undefined : option.option_id)
                }
                columns={COLUMNS}
              />
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
