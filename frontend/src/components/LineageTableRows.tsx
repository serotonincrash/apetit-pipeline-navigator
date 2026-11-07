import type { MetricSource } from "@/api/generated/model";
import { ArtifactRowsTable } from "@/components/ArtifactRowsTable";
import { count } from "@/lib/format";
import { filterInWords, tableLabel } from "@/lib/labels";

/** One lineage table: the filter in words and the rows that contribute to the number. */
export function LineageTableRows({ source }: { source: MetricSource }) {
  return (
    <section className="mb-6">
      <h3 className="font-semibold">{tableLabel(source.artifact.name)}</h3>
      <p className="mt-0.5">{filterInWords(source.artifact.name, source.filters)}</p>
      <p className="mb-2 mt-0.5 text-muted-foreground">
        {count(source.row_count)} contributing rows of {count(source.artifact.row_count)}
      </p>
      {/* A printed report keeps the filter and the count; the rows stay in the app. */}
      <div className="print:hidden">
        <ArtifactRowsTable
          artifactId={source.artifact.artifact_id}
          filters={source.filters}
          knownTotal={source.row_count}
        />
      </div>
    </section>
  );
}
