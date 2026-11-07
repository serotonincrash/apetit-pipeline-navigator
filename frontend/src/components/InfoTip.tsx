import { Info } from "lucide-react";
import { useId } from "react";

interface InfoTipProps {
  term: string;
  children: string;
}

/** Explains a term on hover or keyboard focus. */
export function InfoTip({ term, children }: InfoTipProps) {
  const id = useId();
  return (
    <span className="group relative ml-1 inline-flex align-middle">
      <button
        type="button"
        aria-label={`Explain ${term}`}
        aria-describedby={id}
        className="text-muted-foreground hover:text-foreground"
      >
        <Info aria-hidden="true" className="size-3.5" />
      </button>
      <span
        id={id}
        role="tooltip"
        className="absolute left-0 top-full z-10 mt-1 hidden w-64 rounded-md border bg-background p-2 text-xs text-foreground group-focus-within:block group-hover:block"
      >
        {children}
      </span>
    </span>
  );
}
