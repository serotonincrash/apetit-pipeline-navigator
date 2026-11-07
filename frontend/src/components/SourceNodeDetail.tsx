import type { MetricSources } from "@/api/generated/model";
import { CorrectionsList } from "@/components/CorrectionsList";
import { LineageTableRows } from "@/components/LineageTableRows";
import { stepLabel } from "@/lib/labels";
import type { PathNode } from "@/lib/sourcePath";

interface SourceNodeDetailProps {
  node: PathNode;
  sources: MetricSources;
}

/** The details of the step picked in the path. */
export function SourceNodeDetail({ node, sources }: SourceNodeDetailProps) {
  const { step } = node;
  const isCorrections = step.step === "apply_approved";
  const isRaw = step.step === "load_raw";
  return (
    <div className="p-4">
      <h3 className="text-base font-semibold">
        {isRaw ? "Raw package files" : stepLabel(step.step)}
      </h3>
      <p className="mt-1 text-muted-foreground">{step.summary}</p>

      {node.tables.length > 0 ? (
        <div className="mt-4">
          {node.tables.map((source) => (
            <LineageTableRows key={source.artifact.artifact_id} source={source} />
          ))}
        </div>
      ) : (
        <p className="mt-4">
          This step fed the number. The app does not keep row-level detail for it.
        </p>
      )}

      {isCorrections ? (
        <section className="mt-4">
          <h3 className="mb-2 font-semibold">Corrections applied</h3>
          <CorrectionsList corrections={sources.corrections} />
        </section>
      ) : null}
    </div>
  );
}
