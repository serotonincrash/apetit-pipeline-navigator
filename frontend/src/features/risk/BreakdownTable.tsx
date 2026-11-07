import type { Metric } from "@/api/generated/model";
import { MetricNumber } from "@/components/MetricNumber";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { unitLabel } from "@/lib/format";
import { climateLabel, cropLabel, regionLabel } from "@/lib/labels";
import { type RiskRow, SCENARIO_ORDER } from "@/lib/risk";

interface BreakdownTableProps {
  rows: RiskRow[];
  badYears: Map<string, Record<string, Metric>>;
}

function scenarioHeading(scenario: string): string {
  return scenario === "baseline" ? "Today" : climateLabel(scenario);
}

export function BreakdownTable({ rows, badYears }: BreakdownTableProps) {
  const unit = rows.flatMap((row) => Object.values(row.byScenario)).find(Boolean)?.unit ?? "";
  return (
    <Table>
      <TableHead>
        <tr>
          <TableHeaderCell rowSpan={2}>Crop</TableHeaderCell>
          <TableHeaderCell rowSpan={2}>Region</TableHeaderCell>
          <TableHeaderCell numeric colSpan={SCENARIO_ORDER.length}>
            {unitLabel(unit)}
          </TableHeaderCell>
          <TableHeaderCell numeric colSpan={SCENARIO_ORDER.length}>
            Chance of a bad year, % of seasons, with range
          </TableHeaderCell>
        </tr>
        <tr>
          {SCENARIO_ORDER.map((scenario) => (
            <TableHeaderCell key={`cost-${scenario}`} numeric>
              {scenarioHeading(scenario)}
            </TableHeaderCell>
          ))}
          {SCENARIO_ORDER.map((scenario) => (
            <TableHeaderCell key={`bad-${scenario}`} numeric>
              {scenarioHeading(scenario)}
            </TableHeaderCell>
          ))}
        </tr>
      </TableHead>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key}>
            <TableCell>{cropLabel(row.crop)}</TableCell>
            <TableCell>{regionLabel(row.region)}</TableCell>
            {SCENARIO_ORDER.map((scenario) => {
              const metric = row.byScenario[scenario];
              return (
                <TableCell key={scenario} numeric>
                  {metric ? <MetricNumber metric={metric} /> : null}
                </TableCell>
              );
            })}
            {SCENARIO_ORDER.map((scenario) => {
              const metric = badYears.get(row.key)?.[scenario];
              return (
                <TableCell key={`bad-${scenario}`} numeric>
                  {metric ? <MetricNumber metric={metric} showRange /> : null}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
