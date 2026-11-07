import { ChevronDown } from "lucide-react";
import { Fragment } from "react";
import { count } from "@/lib/format";
import { stepLabel, tableLabel } from "@/lib/labels";
import type { PathNode } from "@/lib/sourcePath";
import { cn } from "@/lib/utils";

interface SourcesPathProps {
  nodes: PathNode[];
  selected: string | undefined;
  correctionCount: number;
  headline: string;
  onSelect: (stepRunId: string) => void;
}

function nodeTitle(node: PathNode): string {
  return node.step.step === "load_raw" ? "Raw package files" : stepLabel(node.step.step);
}

function nodeNote(node: PathNode, correctionCount: number): string[] {
  const notes = node.tables.map(
    (source) => `${tableLabel(source.artifact.name)}: ${count(source.row_count)} rows`,
  );
  if (node.step.step === "apply_approved") notes.push(`${count(correctionCount)} corrections`);
  return notes;
}

/** The steps behind a number, from the number back to the raw package files. */
export function SourcesPath({
  nodes,
  selected,
  correctionCount,
  headline,
  onSelect,
}: SourcesPathProps) {
  return (
    <ol className="p-4">
      <li className="border bg-muted px-3 py-2 font-medium">{headline}</li>
      {nodes.map((node) => (
        <Fragment key={node.step.step_run_id}>
          <li aria-hidden="true" className="flex justify-center py-0.5 text-muted-foreground">
            <ChevronDown className="size-4" />
          </li>
          <li>
            <button
              type="button"
              onClick={() => onSelect(node.step.step_run_id)}
              aria-current={selected === node.step.step_run_id}
              className={cn(
                "w-full border px-3 py-2 text-left hover:bg-muted",
                selected === node.step.step_run_id && "border-primary bg-selected",
              )}
            >
              <span className="block font-medium">{nodeTitle(node)}</span>
              {nodeNote(node, correctionCount).map((note) => (
                <span key={note} className="block text-muted-foreground">
                  {note}
                </span>
              ))}
            </button>
          </li>
        </Fragment>
      ))}
    </ol>
  );
}
