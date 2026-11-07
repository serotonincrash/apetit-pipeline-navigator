import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useListProposals } from "@/api/generated/client";
import type { Artifact, StepRun } from "@/api/generated/model";
import { ArtifactRowsTable } from "@/components/ArtifactRowsTable";
import { StatusLabel } from "@/components/StatusLabel";
import { Button } from "@/components/ui/button";
import type { LiveSection } from "@/features/runs/useRunEvents";
import { count, duration } from "@/lib/format";
import { sentenceCase, stepLabel, tableLabel } from "@/lib/labels";

interface StepItemProps {
  runId: string;
  step: StepRun;
  tables: Artifact[];
  sections: LiveSection[];
}

function FixesWaiting({ runId, message }: { runId: string; message: string }) {
  const open = useListProposals({ run_id: runId, status: "open", limit: 1 });
  const waiting = (open.data?.total ?? 0) > 0 || /waiting for review/i.test(message);
  if (!waiting) return null;
  return (
    <Link
      to="/review/data"
      search={{ status: "open" }}
      className="mt-2 inline-block text-primary underline"
    >
      Open data review
    </Link>
  );
}

export function StepItem({ runId, step, tables, sections }: StepItemProps) {
  const [openTable, setOpenTable] = useState<string>();
  const shown = tables.find((table) => table.artifact_id === openTable);

  return (
    <li className="relative border-l pb-6 pl-6 last:pb-0">
      <span
        aria-hidden="true"
        className="absolute -left-1.5 top-1.5 size-3 rounded-full border bg-background"
      />
      <div className="flex items-baseline gap-3">
        <h2 className="font-semibold">{stepLabel(step.step)}</h2>
        <StatusLabel status={step.status} />
        {step.seconds !== null ? (
          <span className="text-muted-foreground">{duration(step.seconds)}</span>
        ) : null}
      </div>
      <p className="mt-0.5 max-w-column text-muted-foreground">{step.summary}</p>

      {sections.length > 0 ? (
        <ul className="mt-2 max-w-column">
          {sections.map((section) => (
            <li key={section.name} className="flex gap-3 py-0.5">
              <span className="flex-1">
                <span className="font-medium">{sentenceCase(section.name)}</span>
                <span className="text-muted-foreground">. {section.annotation}</span>
              </span>
              <span className="tabular-nums text-muted-foreground">
                {section.seconds === null
                  ? step.status === "failed"
                    ? "Stopped"
                    : "Running"
                  : duration(section.seconds)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {step.status === "failed" && step.error ? (
        <div className="mt-2 max-w-column border-l-2 border-danger pl-3" role="alert">
          <p className="text-danger">{step.error}</p>
          <FixesWaiting runId={runId} message={step.error} />
        </div>
      ) : null}

      {tables.length > 0 ? (
        <div className="mt-2">
          <p className="text-xs text-muted-foreground">Tables written</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {tables.map((table) => (
              <Button
                key={table.artifact_id}
                size="sm"
                aria-pressed={openTable === table.artifact_id}
                onClick={() =>
                  setOpenTable(openTable === table.artifact_id ? undefined : table.artifact_id)
                }
              >
                {tableLabel(table.name)}, {count(table.row_count)} rows
              </Button>
            ))}
          </div>
          {shown ? (
            <div className="mt-2">
              <ArtifactRowsTable artifactId={shown.artifact_id} knownTotal={shown.row_count} />
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
