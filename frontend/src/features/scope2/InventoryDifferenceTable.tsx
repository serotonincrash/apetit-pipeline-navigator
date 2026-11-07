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

interface InventoryDifferenceTableProps {
  location: Metric[];
  market: Metric[];
}

/** Our Scope 2 minus the answer inventory, by year. */
export function InventoryDifferenceTable({ location, market }: InventoryDifferenceTableProps) {
  const years = [...new Set([...location, ...market].map((metric) => metric.period ?? ""))].sort();
  const find = (metrics: Metric[], year: string) =>
    metrics.find((metric) => (metric.period ?? "") === year);
  return (
    <Table>
      <TableHead>
        <tr>
          <TableHeaderCell>Inventory year</TableHeaderCell>
          <TableHeaderCell numeric>Location-based difference, t CO2e</TableHeaderCell>
          <TableHeaderCell numeric>Market-based difference, t CO2e</TableHeaderCell>
        </tr>
      </TableHead>
      <TableBody>
        {years.map((year) => {
          const locationMetric = find(location, year);
          const marketMetric = find(market, year);
          return (
            <TableRow key={year}>
              <TableCell className="tabular-nums">{year}</TableCell>
              <TableCell numeric>
                {locationMetric ? <MetricNumber metric={locationMetric} /> : null}
              </TableCell>
              <TableCell numeric>
                {marketMetric ? <MetricNumber metric={marketMetric} /> : null}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
