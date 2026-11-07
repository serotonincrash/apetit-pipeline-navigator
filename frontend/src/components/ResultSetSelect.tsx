import type { ResultSet } from "@/api/generated/model";
import { Select } from "@/components/ui/select";
import { dateAndTime } from "@/lib/format";
import { statusLabel } from "@/lib/labels";

interface ResultSetSelectProps {
  resultSets: ResultSet[];
  resultSetId: string;
  onChange: (id: string) => void;
}

/** Picks which run's results a screen shows. */
export function ResultSetSelect({ resultSets, resultSetId, onChange }: ResultSetSelectProps) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">Results</span>
      <Select value={resultSetId} onChange={(event) => onChange(event.target.value)}>
        {resultSets.map((set) => (
          <option key={set.result_set_id} value={set.result_set_id}>
            {set.run_id}, {statusLabel(set.status)}, {dateAndTime(set.created_at)}
          </option>
        ))}
      </Select>
    </label>
  );
}
