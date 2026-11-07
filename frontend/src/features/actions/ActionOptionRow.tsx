import type { Action, ActionOption, Assumption, Metric } from "@/api/generated/model";
import { MetricNumber } from "@/components/MetricNumber";
import { StatusLabel } from "@/components/StatusLabel";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { ActionOptionDetail } from "@/features/actions/ActionOptionDetail";
import { RiskRemovedBar } from "@/features/actions/RiskRemovedBar";
import { euros } from "@/lib/format";

export interface OptionMetrics {
  riskRemoved?: Metric;
  emissionsRemoved?: Metric;
}

interface ActionOptionRowProps {
  option: ActionOption;
  action: Action | undefined;
  metrics: OptionMetrics;
  assumptions: Assumption[];
  maxRiskRemoved: number;
  resultSetId: string;
  canDecide: boolean;
  open: boolean;
  onToggle: () => void;
  columns: number;
}

export function ActionOptionRow(props: ActionOptionRowProps) {
  const { option, action, metrics, open } = props;
  return (
    <>
      <TableRow>
        <TableCell>
          <span className="font-medium">{action?.short_name ?? option.name}</span>
        </TableCell>
        <TableCell numeric>
          {option.cost_eur_per_yr === null ? "Not known" : euros(option.cost_eur_per_yr)}
        </TableCell>
        <TableCell numeric>
          {metrics.riskRemoved ? <MetricNumber metric={metrics.riskRemoved} /> : null}
        </TableCell>
        <TableCell>
          {metrics.riskRemoved ? (
            <RiskRemovedBar value={metrics.riskRemoved.value} max={props.maxRiskRemoved} />
          ) : null}
        </TableCell>
        <TableCell numeric>
          {metrics.emissionsRemoved ? <MetricNumber metric={metrics.emissionsRemoved} /> : null}
        </TableCell>
        <TableCell>{option.status ? <StatusLabel status={option.status} /> : null}</TableCell>
        <TableCell>
          <Button size="sm" aria-expanded={open} onClick={props.onToggle}>
            {open ? "Hide details" : "Show details"}
          </Button>
        </TableCell>
      </TableRow>
      {open ? (
        <TableRow>
          <td colSpan={props.columns} className="bg-muted/40">
            <ActionOptionDetail
              option={option}
              action={action}
              assumptions={props.assumptions}
              resultSetId={props.resultSetId}
              canDecide={props.canDecide}
            />
          </td>
        </TableRow>
      ) : null}
    </>
  );
}
