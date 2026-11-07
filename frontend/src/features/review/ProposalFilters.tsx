import { Select } from "@/components/ui/select";
import { tableLabel } from "@/lib/labels";

export interface FilterOptions {
  rules: string[];
  tables: string[];
}

interface ProposalFiltersProps {
  options: FilterOptions;
  rule: string | undefined;
  table: string | undefined;
  status: string | undefined;
  onChange: (next: { rule?: string; table?: string; status?: string }) => void;
}

const STATUSES: [string, string][] = [
  ["open", "Open"],
  ["approved", "Approved"],
  ["rejected", "Rejected"],
  ["flag", "Flag"],
];

export function ProposalFilters({ options, rule, table, status, onChange }: ProposalFiltersProps) {
  const set = (key: "rule" | "table" | "status") => (value: string) =>
    onChange({ rule, table, status, [key]: value || undefined });
  return (
    <div className="flex items-center gap-4">
      <label className="flex items-center gap-2">
        <span className="text-muted-foreground">Data check</span>
        <Select value={rule ?? ""} onChange={(event) => set("rule")(event.target.value)}>
          <option value="">All</option>
          {options.rules.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex items-center gap-2">
        <span className="text-muted-foreground">Table</span>
        <Select value={table ?? ""} onChange={(event) => set("table")(event.target.value)}>
          <option value="">All</option>
          {options.tables.map((name) => (
            <option key={name} value={name}>
              {tableLabel(name)}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex items-center gap-2">
        <span className="text-muted-foreground">Status</span>
        <Select value={status ?? ""} onChange={(event) => set("status")(event.target.value)}>
          <option value="">All</option>
          {STATUSES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </label>
    </div>
  );
}
