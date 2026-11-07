import type { Insight, Metric } from "@/api/generated/model";
import { MetricNumber } from "@/components/MetricNumber";
import { metricValue, valueWithUnit } from "@/lib/format";
import { splitTokens } from "./reportTokens";

interface TokenTextProps {
  text: string;
  metrics: Record<string, Metric>;
  /** Left out inside an insight, so an insight never cites another one. */
  insights?: Insight[];
}

/** Drafted text with each cited number shown by the shared number component, with its unit. */
export function TokenText({ text, metrics, insights }: TokenTextProps) {
  return (
    <>
      {splitTokens(text).map((piece, index) => {
        // Pieces never reorder, so the position is a stable key.
        const key = `${piece.kind}-${index}`;
        if (piece.kind === "text") return <span key={key}>{piece.text}</span>;
        if (piece.kind === "metric") {
          const metric = metrics[piece.id];
          if (!metric) return <span key={key}>(number missing)</span>;
          const unit = valueWithUnit(metric.unit, metric.value).slice(
            metricValue(metric.unit, metric.value).length,
          );
          return (
            <span key={key}>
              <MetricNumber metric={metric} />
              {unit}
            </span>
          );
        }
        const insight = insights?.find((candidate) => candidate.insight_id === piece.id);
        return insight ? (
          <TokenText key={key} text={insight.text} metrics={metrics} />
        ) : (
          <span key={key}>(insight missing)</span>
        );
      })}
    </>
  );
}
