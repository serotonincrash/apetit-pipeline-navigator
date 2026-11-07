import { Input } from "@/components/ui/input";
import { TableCell, TableRow } from "@/components/ui/table";
import type { EditableValue } from "@/lib/assumptionOverrides";
import { plainNumber } from "@/lib/format";

interface AssumptionFieldProps {
  item: EditableValue;
  draft: string | undefined;
  onChange: (id: string, value: string) => void;
}

/** One editable assumption: its label, an input holding the value, unit and source. */
export function AssumptionField({ item, draft, onChange }: AssumptionFieldProps) {
  return (
    <TableRow>
      <TableCell>
        <label htmlFor={item.id}>{item.label}</label>
      </TableCell>
      <TableCell numeric>
        <Input
          id={item.id}
          inputMode="decimal"
          className="w-24 text-right tabular-nums"
          value={draft ?? String(item.original)}
          onChange={(event) => onChange(item.id, event.target.value)}
          aria-describedby={`${item.id}-was`}
        />
        <span id={`${item.id}-was`} className="sr-only">
          Current value {plainNumber(item.original)}
        </span>
      </TableCell>
      <TableCell>{item.unit}</TableCell>
      <TableCell className="text-muted-foreground">{item.source}</TableCell>
    </TableRow>
  );
}
