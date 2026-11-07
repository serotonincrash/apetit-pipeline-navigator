import { climateLabel } from "@/lib/labels";
import { scenarioColour } from "@/lib/theme";

/** The colour key for climate scenarios. Today is a hollow dot, the others are filled. */
export function ScenarioLegend({ scenarios }: { scenarios: string[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-5 gap-y-1">
      {scenarios.map((scenario) => (
        <li key={scenario} className="flex items-center gap-1.5">
          <svg width="12" height="12" aria-hidden="true">
            <circle
              cx="6"
              cy="6"
              r="4.5"
              fill={scenario === "baseline" ? "none" : scenarioColour(scenario)}
              stroke={scenarioColour(scenario)}
              strokeWidth="1.5"
            />
          </svg>
          {scenario === "baseline" ? "Today (1991–2020 weather)" : climateLabel(scenario)}
        </li>
      ))}
    </ul>
  );
}
