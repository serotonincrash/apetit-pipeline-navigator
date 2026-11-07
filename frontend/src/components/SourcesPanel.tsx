import { useMemo, useState } from "react";
import { useGetMetricSources, useGetRun } from "@/api/generated/client";
import type { MetricSources, RunDetail } from "@/api/generated/model";
import { AssumptionsList } from "@/components/AssumptionsList";
import { ErrorState } from "@/components/ErrorState";
import { SidePanel } from "@/components/SidePanel";
import { SourceNodeDetail } from "@/components/SourceNodeDetail";
import { SourcesPath } from "@/components/SourcesPath";
import { TableSkeleton } from "@/components/TableSkeleton";
import { metricTitle } from "@/lib/metricTitle";
import { buildPath } from "@/lib/sourcePath";

interface SourcesBodyProps {
  sources: MetricSources;
  run: RunDetail | undefined;
}

function SourcesBody({ sources, run }: SourcesBodyProps) {
  const nodes = useMemo(() => (run ? buildPath(run, sources.sources) : []), [run, sources.sources]);
  const [picked, setPicked] = useState<string>();
  const selectedId = picked ?? nodes[0]?.step.step_run_id;
  const node = nodes.find((candidate) => candidate.step.step_run_id === selectedId);

  return (
    <div className="flex min-h-full flex-col">
      <div className="grid flex-1 grid-cols-[18rem_1fr] border-b">
        <div className="border-r">
          <SourcesPath
            nodes={nodes}
            selected={selectedId}
            correctionCount={sources.corrections.length}
            headline={metricTitle(sources.metric)}
            onSelect={setPicked}
          />
        </div>
        <div className="min-w-0">
          {node ? (
            <SourceNodeDetail node={node} sources={sources} />
          ) : (
            <p className="p-4 text-muted-foreground">
              No tables are recorded for this number. Its assumptions are listed below.
            </p>
          )}
        </div>
      </div>
      <section className="p-4">
        <h3 className="mb-2 font-semibold">Assumptions</h3>
        <AssumptionsList assumptions={sources.assumptions} />
      </section>
    </div>
  );
}

export function SourcesPanel({ metricId, onClose }: { metricId: string; onClose: () => void }) {
  const sources = useGetMetricSources(metricId);
  const runId = sources.data?.sources[0]?.artifact.run_id ?? "";
  const run = useGetRun(runId, { query: { enabled: runId !== "" } });

  return (
    <SidePanel title="Sources" onClose={onClose} wide>
      {sources.isPending ? (
        <div className="p-4">
          <TableSkeleton rows={10} />
        </div>
      ) : null}
      {sources.isError ? (
        <div className="p-4">
          <ErrorState
            title="The sources did not load."
            message="Close the panel and click the number again."
            onRetry={() => void sources.refetch()}
          />
        </div>
      ) : null}
      {sources.data ? <SourcesBody key={metricId} sources={sources.data} run={run.data} /> : null}
    </SidePanel>
  );
}
