import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  getExportReportUrl,
  getGetReportQueryKey,
  getListResultSetsQueryKey,
  getListRunsQueryKey,
  useDecideResultSet,
  useRequestReport,
} from "@/api/generated/client";
import type { ResultSet } from "@/api/generated/model";
import { requireName, usePersona } from "@/api/persona";
import { Button } from "@/components/ui/button";
import { messageOf } from "@/lib/errors";

interface ReportBarProps {
  resultSet: ResultSet;
  hasDraft: boolean;
  /** A draft is being written, so a new one cannot be asked for yet. */
  drafting: boolean;
}

const NEXT_MOVE = {
  draft: { status: "in_review", label: "Send for review" },
  in_review: { status: "approved", label: "Approve results" },
  approved: { status: "published", label: "Publish report" },
} as const;

/** The review and publish controls. The bar does not print. */
export function ReportBar({ resultSet, hasDraft, drafting }: ReportBarProps) {
  const queryClient = useQueryClient();
  const isSpecialist = usePersona().role === "sustainability_specialist";
  const [confirming, setConfirming] = useState(false);
  const id = resultSet.result_set_id;
  const request = useRequestReport({
    mutation: {
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: getListRunsQueryKey() }),
    },
  });
  const decide = useDecideResultSet({
    mutation: {
      onSuccess: () => {
        setConfirming(false);
        void queryClient.invalidateQueries({ queryKey: getListResultSetsQueryKey() });
        void queryClient.invalidateQueries({ queryKey: getGetReportQueryKey(id) });
      },
    },
  });

  const status = resultSet.status;
  const next =
    status === "draft" || status === "in_review" || status === "approved"
      ? NEXT_MOVE[status]
      : null;
  const canRedraft = status === "draft" || status === "in_review";
  const error = request.error ?? decide.error;

  const askForDraft = () => {
    if (requireName()) request.mutate({ resultSetId: id });
  };
  const move = () => {
    if (next && requireName()) decide.mutate({ resultSetId: id, data: { status: next.status } });
  };

  return (
    <div className="space-y-2 print:hidden">
      <div className="flex flex-wrap items-center gap-3 border bg-muted px-3 py-2">
        {isSpecialist ? (
          <>
            {canRedraft ? (
              <Button disabled={drafting || request.isPending} onClick={askForDraft}>
                {hasDraft ? "Draft again" : "Request a draft"}
              </Button>
            ) : null}
            {next && confirming ? (
              <>
                <p>
                  Publishing makes this the report management reads. It replaces the earlier
                  published report.
                </p>
                <Button variant="primary" disabled={decide.isPending} onClick={move}>
                  Publish now
                </Button>
                <Button onClick={() => setConfirming(false)}>Cancel</Button>
              </>
            ) : null}
            {next && !confirming ? (
              <Button
                variant="primary"
                disabled={!hasDraft || drafting || decide.isPending}
                onClick={status === "approved" ? () => setConfirming(true) : move}
              >
                {next.label}
              </Button>
            ) : null}
          </>
        ) : (
          <p className="text-muted-foreground">
            The sustainability specialist drafts, approves and publishes this report.
          </p>
        )}
        <span className="ml-auto flex items-center gap-3">
          {status === "published" ? (
            <a className="text-primary underline" href={getExportReportUrl(id)} download>
              Export as Markdown
            </a>
          ) : null}
          <Button onClick={() => window.print()}>Print or save as PDF</Button>
        </span>
      </div>
      {error ? (
        <p role="alert" className="text-danger">
          {messageOf(error) ?? "The request did not go through. Try again."}
        </p>
      ) : null}
    </div>
  );
}
