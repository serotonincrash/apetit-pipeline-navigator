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
import { cn } from "@/lib/utils";

interface Scope2TableProps {
  use: Metric[];
  location: Metric[];
  market: Metric[];
}

interface Scope2Row {
  key: string;
  year: string;
  site: string | null;
  use: Metric | undefined;
  location: Metric | undefined;
  market: Metric | undefined;
}

/** One row per site and year, newest year first, each year closed by its total across sites. */
function rowsOf({ use, location, market }: Scope2TableProps): Scope2Row[] {
  const rows = new Map<string, Scope2Row>();
  const put = (column: "use" | "location" | "market", metrics: Metric[]) => {
    for (const metric of metrics) {
      const year = metric.period ?? "";
      const key = `${year}|${metric.site ?? ""}`;
      const row = rows.get(key) ?? {
        key,
        year,
        site: metric.site,
        use: undefined,
        location: undefined,
        market: undefined,
      };
      row[column] = metric;
      rows.set(key, row);
    }
  };
  put("use", use);
  put("location", location);
  put("market", market);
  const rank = (row: Scope2Row) => (row.site === null ? 1 : 0);
  return [...rows.values()].sort(
    (a, b) =>
      b.year.localeCompare(a.year) ||
      rank(a) - rank(b) ||
      (a.site ?? "").localeCompare(b.site ?? ""),
  );
}

function Cell({ metric }: { metric: Metric | undefined }) {
  return <TableCell numeric>{metric ? <MetricNumber metric={metric} /> : null}</TableCell>;
}

/** Electricity use and Scope 2 for each site and year. The unit is in the column header. */
export function Scope2Table(props: Scope2TableProps) {
  const rows = rowsOf(props);
  return (
    <Table>
      <TableHead>
        <tr>
          <TableHeaderCell>Year</TableHeaderCell>
          <TableHeaderCell>Site</TableHeaderCell>
          <TableHeaderCell numeric>Electricity use, MWh</TableHeaderCell>
          <TableHeaderCell numeric>Location-based Scope 2, t CO2e</TableHeaderCell>
          <TableHeaderCell numeric>Market-based Scope 2, t CO2e</TableHeaderCell>
        </tr>
      </TableHead>
      <TableBody>
        {rows.map((row, index) => (
          <TableRow key={row.key} className={cn(row.site === null && "bg-muted font-medium")}>
            <TableCell className="tabular-nums">
              {rows[index - 1]?.year === row.year ? null : row.year}
            </TableCell>
            <TableCell>{row.site ?? "All sites"}</TableCell>
            <Cell metric={row.use} />
            <Cell metric={row.location} />
            <Cell metric={row.market} />
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
