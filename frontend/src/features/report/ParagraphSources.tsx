import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import { cn } from "@/lib/utils";
import { MetricLineage } from "./MetricLineage";

/**
 * A disclosure group under a paragraph, with the lineage of every number it cites. The content is
 * always in the page, so printing shows it open.
 */
export function ParagraphSources({ metricIds }: { metricIds: string[] }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  if (metricIds.length === 0) return null;
  const label = `Sources for ${metricIds.length} ${metricIds.length === 1 ? "number" : "numbers"}`;
  return (
    <section className="mt-2 border-t">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 py-1.5 text-muted-foreground hover:text-foreground print:hidden"
      >
        <ChevronRight
          aria-hidden="true"
          className={cn("size-4 transition-transform", open && "rotate-90")}
        />
        {label}
      </button>
      <p className="hidden py-1.5 font-medium print:block">{label}</p>
      <div
        id={panelId}
        className={cn("space-y-8 pb-4 pt-2", open ? "block" : "hidden print:block")}
      >
        {metricIds.map((metricId) => (
          <MetricLineage key={metricId} metricId={metricId} />
        ))}
      </div>
    </section>
  );
}
