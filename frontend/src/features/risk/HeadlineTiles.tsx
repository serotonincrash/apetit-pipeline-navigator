import type { Metric } from "@/api/generated/model";
import { MetricNumber } from "@/components/MetricNumber";
import { unitLabel } from "@/lib/format";
import { climateLabel, measureLabel } from "@/lib/labels";
import { SCENARIO_ORDER } from "@/lib/risk";
import { scenarioColour } from "@/lib/theme";

/** Totals over all crops and regions, one per climate scenario. */
export function HeadlineTiles({ totals }: { totals: Record<string, Metric> }) {
  const tiles = SCENARIO_ORDER.map((scenario) => ({ scenario, metric: totals[scenario] })).filter(
    (tile): tile is { scenario: (typeof SCENARIO_ORDER)[number]; metric: Metric } =>
      tile.metric !== undefined,
  );
  if (tiles.length === 0) return null;
  const first = tiles[0]?.metric;
  return (
    <section aria-label="Totals">
      <p className="mb-2 text-muted-foreground">
        {first
          ? `${measureLabel(first.name)}, all crops and regions, ${unitLabel(first.unit)}`
          : ""}
      </p>
      <div className="grid grid-cols-4 gap-4">
        {tiles.map(({ scenario, metric }) => (
          <div key={scenario} className="border-l pl-3">
            <p className="text-2xl font-semibold">
              <MetricNumber metric={metric} />
            </p>
            <p className="flex items-center gap-1.5 text-muted-foreground">
              <svg width="10" height="10" aria-hidden="true">
                <circle
                  cx="5"
                  cy="5"
                  r="4"
                  fill={scenario === "baseline" ? "none" : scenarioColour(scenario)}
                  stroke={scenarioColour(scenario)}
                  strokeWidth="1.5"
                />
              </svg>
              {scenario === "baseline" ? "Today (1991\u20132020 weather)" : climateLabel(scenario)}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
