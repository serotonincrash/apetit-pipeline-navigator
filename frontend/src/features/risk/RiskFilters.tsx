import type { ResultSet } from "@/api/generated/model";
import { Select } from "@/components/ui/select";
import { dateAndTime } from "@/lib/format";
import {
  CROP_CODES,
  climateLabel,
  cropLabel,
  FUTURE_SCENARIOS,
  REGION_CODES,
  regionLabel,
  statusLabel,
  TRANSITION_BY_CLIMATE,
  transitionLabel,
} from "@/lib/labels";
import type { TransitionChoice } from "@/lib/risk";

interface RiskFiltersProps {
  resultSets: ResultSet[];
  resultSetId: string;
  crop: string | undefined;
  region: string | undefined;
  choice: TransitionChoice;
  onResultSet: (id: string) => void;
  onCrop: (crop: string | undefined) => void;
  onRegion: (region: string | undefined) => void;
  onTransition: (scenario: string, ngfs: string) => void;
}

export function RiskFilters(props: RiskFiltersProps) {
  return (
    <div className="space-y-3">
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
          <span className="text-xs text-muted-foreground">Crop</span>
          <Select
            value={props.crop ?? ""}
            onChange={(event) => props.onCrop(event.target.value || undefined)}
          >
            <option value="">All crops</option>
            {CROP_CODES.map((code) => (
              <option key={code} value={code}>
                {cropLabel(code)}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Region</span>
          <Select
            value={props.region ?? ""}
            onChange={(event) => props.onRegion(event.target.value || undefined)}
          >
            <option value="">All regions</option>
            {REGION_CODES.map((code) => (
              <option key={code} value={code}>
                {regionLabel(code)}
              </option>
            ))}
          </Select>
        </label>
      </div>
      <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
        {FUTURE_SCENARIOS.map((scenario) => (
          <label key={scenario} className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">
              Transition scenario with {climateLabel(scenario)}
            </span>
            <Select
              value={props.choice[scenario]}
              onChange={(event) => props.onTransition(scenario, event.target.value)}
            >
              {(TRANSITION_BY_CLIMATE[scenario] ?? []).map((code) => (
                <option key={code} value={code}>
                  {transitionLabel(code)}
                </option>
              ))}
            </Select>
          </label>
        ))}
      </div>
    </div>
  );
}
