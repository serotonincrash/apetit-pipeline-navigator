import type { Metric } from "@/api/generated/model";
import { useSources } from "@/components/SourcesContext";
import { metricValue, rangeText } from "@/lib/format";
import { cn } from "@/lib/utils";

interface MetricNumberProps {
  metric: Metric;
  showRange?: boolean;
  className?: string;
}

/** Every result number in the app. Clicking it opens the sources behind it. */
export function MetricNumber({ metric, showRange, className }: MetricNumberProps) {
  const { openSources } = useSources();
  const text = metricValue(metric.unit, metric.value);
  const range =
    showRange && metric.low !== null && metric.high !== null
      ? rangeText(metric.unit, metric.low, metric.high)
      : null;
  return (
    <span className={cn("inline-block", className)}>
      <button
        type="button"
        title="Show sources"
        onClick={() => openSources(metric.metric_id)}
        className="tabular-nums underline decoration-dotted underline-offset-4 hover:decoration-solid"
      >
        {text}
      </button>
      {range ? <span className="block text-xs text-muted-foreground">{range}</span> : null}
    </span>
  );
}
