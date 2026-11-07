import type { ResultSet } from "@/api/generated/model";
import { Select } from "@/components/ui/select";
import { dateAndTime } from "@/lib/format";
import { climateLabel, statusLabel } from "@/lib/labels";
import { SCENARIO_ORDER } from "@/lib/risk";

interface ActionFiltersProps {
  resultSets: ResultSet[];
  resultSetId: string;
  scenario: string;
  onResultSet: (id: string) => void;
  onScenario: (scenario: string) => void;
}

export function ActionFilters(props: ActionFiltersProps) {
  return (
    <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">Results</span>
        <Select
          value={props.resultSetId}
          onChange={(event) => props.onResultSet(event.target.value)}
        >
          {props.resultSets.map((set) => (
            <option key={set.result_set_id} value={set.result_set_id}>
              {set.run_id}, {statusLabel(set.status)}, {dateAndTime(set.created_at)}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">Climate scenario</span>
        <Select value={props.scenario} onChange={(event) => props.onScenario(event.target.value)}>
          {SCENARIO_ORDER.map((code) => (
            <option key={code} value={code}>
              {climateLabel(code)}
            </option>
          ))}
        </Select>
      </label>
    </div>
  );
}
