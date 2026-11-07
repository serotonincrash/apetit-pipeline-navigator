import { MEASURES, type Measure } from "@/lib/risk";
import { cn } from "@/lib/utils";

interface MeasureSwitchProps {
  value: Measure;
  onChange: (measure: Measure) => void;
}

export function MeasureSwitch({ value, onChange }: MeasureSwitchProps) {
  return (
    <fieldset className="m-0 inline-flex border p-0">
      <legend className="sr-only">Measure</legend>
      {MEASURES.map((measure) => (
        <button
          key={measure.id}
          type="button"
          aria-pressed={value === measure.id}
          onClick={() => onChange(measure.id)}
          className={cn(
            "h-8 border-r px-3 last:border-r-0",
            value === measure.id ? "bg-primary text-primary-foreground" : "hover:bg-muted",
          )}
        >
          {measure.label}
        </button>
      ))}
    </fieldset>
  );
}
