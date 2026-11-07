import { X } from "lucide-react";
import { type ReactNode, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SidePanelProps {
  title: string;
  onClose: () => void;
  wide?: boolean;
  children: ReactNode;
}

/** A panel fixed to the right edge. Esc closes it. */
export function SidePanel({ title, onClose, wide, children }: SidePanelProps) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      aria-label={title}
      className={cn(
        "fixed inset-y-0 right-0 z-20 flex w-full flex-col border-l bg-background",
        wide ? "max-w-sources" : "max-w-panel",
      )}
    >
      <header className="flex items-center justify-between border-b px-4 py-2.5">
        <h2 className="text-base font-semibold">{title}</h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          aria-label="Close panel"
          title="Close (Esc)"
        >
          <X className="size-4" />
        </Button>
      </header>
      <div className="flex-1 overflow-y-auto">{children}</div>
    </aside>
  );
}
