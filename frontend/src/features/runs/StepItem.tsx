import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { useListProposals } from "@/api/generated/client";
import type { Artifact, StepRun } from "@/api/generated/model";
import { ArtifactRowsTable } from "@/components/ArtifactRowsTable";
import { StatusLabel, statusColour } from "@/components/StatusLabel";
import { Button } from "@/components/ui/button";
import type { LiveSection } from "@/features/runs/useRunEvents";
import { count, duration } from "@/lib/format";
import { sentenceCase, stepLabel, tableLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

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
  // Follows the run until the reader chooses, so a finished step folds away by itself.
  const [chosenOpen, setChosenOpen] = useState<boolean>();
  const shown = tables.find((table) => table.artifact_id === openTable);
  const hasDetail = sections.length > 0 || tables.length > 0;
  const open = hasDetail && (chosenOpen ?? (step.status === "running" || step.status === "failed"));
  const started = step.status !== "pending";

  return (
    <li className="group relative pb-5 pl-6">
      <span
        aria-hidden="true"
        className={cn(
          "absolute inset-y-0 left-0 w-px bg-current group-last:hidden",
          step.status === "succeeded" ? statusColour(step.status) : "text-border",
        )}
      />
      <button
        type="button"
        aria-expanded={hasDetail ? open : undefined}
        disabled={!hasDetail}
        onClick={() => setChosenOpen(!open)}
        className={cn(
          "relative -ml-6 flex w-full items-center gap-2 pl-6 text-left",
          hasDetail && "hover:bg-muted",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "absolute -left-1.5 size-3 rounded-full",
            started ? "bg-current" : "border bg-background",
            statusColour(step.status),
            step.status === "running" && "animate-pulse",
          )}
        />
        <ChevronRight
          aria-hidden="true"
          className={cn(
            "size-4 shrink-0 text-muted-foreground",
            open && "rotate-90",
            !hasDetail && "invisible",
          )}
        />
        <span className="font-semibold">{stepLabel(step.step)}</span>
        <StatusLabel status={step.status} />
        {step.seconds !== null ? (
          <span className="text-muted-foreground">{duration(step.seconds)}</span>
        ) : null}
      </button>
      <p className="mt-0.5 max-w-column text-muted-foreground">{step.summary}</p>

      {step.status === "failed" && step.error ? (
        <div className="mt-2 max-w-column border-l-2 border-danger pl-3" role="alert">
          <p className="text-danger">{step.error}</p>
          <FixesWaiting runId={runId} message={step.error} />
        </div>
      ) : null}

      {open && sections.length > 0 ? (
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

      {open && tables.length > 0 ? (
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
