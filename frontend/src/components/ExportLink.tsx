import { Download } from "lucide-react";
import { getExportArtifactUrl } from "@/api/generated/client";
import { cn } from "@/lib/utils";

interface ExportLinkProps {
  artifactId: string;
  filters?: string[];
  className?: string;
}

/** Downloads the rows of one table, with the given filters, as an Excel file. */
export function ExportLink({ artifactId, filters, className }: ExportLinkProps) {
  return (
    <a
      className={cn("inline-flex items-center gap-1.5 text-primary underline", className)}
      href={getExportArtifactUrl(artifactId, filters?.length ? { filter: filters } : undefined)}
    >
      <Download className="size-3.5" aria-hidden="true" />
      Export to Excel
    </a>
  );
}
