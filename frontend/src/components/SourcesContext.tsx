import { useNavigate, useSearch } from "@tanstack/react-router";
import { createContext, type ReactNode, useCallback, useContext, useMemo } from "react";
import { SourcesPanel } from "@/components/SourcesPanel";

interface SourcesContextValue {
  openSources: (metricId: string) => void;
}

const SourcesContext = createContext<SourcesContextValue | null>(null);

/** Keeps the open number in the address (`sources`), so a link opens its sources. */
export function SourcesProvider({ children }: { children: ReactNode }) {
  const metricId = useSearch({ strict: false, select: (search) => search.sources });
  const navigate = useNavigate();
  const setMetric = useCallback(
    (id: string | undefined) =>
      void navigate({ to: ".", search: (previous) => ({ ...previous, sources: id }) }),
    [navigate],
  );
  const value = useMemo(() => ({ openSources: setMetric }), [setMetric]);
  return (
    <SourcesContext.Provider value={value}>
      {children}
      {metricId ? <SourcesPanel metricId={metricId} onClose={() => setMetric(undefined)} /> : null}
    </SourcesContext.Provider>
  );
}

export function useSources(): SourcesContextValue {
  const context = useContext(SourcesContext);
  if (!context) throw new Error("useSources needs a SourcesProvider above it.");
  return context;
}
