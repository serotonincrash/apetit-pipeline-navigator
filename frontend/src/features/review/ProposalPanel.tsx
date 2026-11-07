import { useGetProposal } from "@/api/generated/client";
import type { Rule } from "@/api/generated/model";
import { ErrorState } from "@/components/ErrorState";
import { StatusLabel } from "@/components/StatusLabel";
import { TableSkeleton } from "@/components/TableSkeleton";
import { BacktestNote } from "@/features/review/BacktestNote";
import { ProposalDecisionForm } from "@/features/review/ProposalDecisionForm";
import type { Decide } from "@/features/review/useProposalDecision";
import { evidenceValueText, fillEvidenceTokens } from "@/lib/evidence";
import { dateAndTime } from "@/lib/format";
import { proposerLabel, sentenceCase, tableLabel } from "@/lib/labels";

interface ProposalPanelProps {
  proposalId: string;
  rule: Rule | undefined;
  canDecide: boolean;
  /** Which form the keyboard asked for: reject or edit. */
  mode: "reject" | "edit" | undefined;
  onMode: (mode: "reject" | "edit" | undefined) => void;
  decide: Decide;
  isPending: boolean;
  error: unknown;
}

export function ProposalPanel({
  proposalId,
  rule,
  canDecide,
  mode,
  onMode,
  decide,
  isPending,
  error,
}: ProposalPanelProps) {
  const proposal = useGetProposal(proposalId);

  if (proposal.isPending)
    return (
      <div className="p-4">
        <TableSkeleton rows={8} />
      </div>
    );
  if (proposal.isError) {
    return (
      <div className="p-4">
        <ErrorState
          title="This suggested fix did not load."
          message="Pick another row, or try again."
          onRetry={() => void proposal.refetch()}
        />
      </div>
    );
  }

  const detail = proposal.data;
  const values = Object.entries(detail.evidence.values);
  return (
    <div className="space-y-4 p-4">
      <div>
        <p className="flex items-center gap-3">
          <span className="font-semibold">
            {detail.action === "fix" ? "Suggested fix" : "Flag"}
          </span>
          {detail.action === "flag" && detail.status === "flag" ? null : (
            <StatusLabel status={detail.status} />
          )}
        </p>
        <p className="mt-1 font-medium">{detail.record_key}</p>
        <p className="text-muted-foreground">
          {tableLabel(detail.table)}, field {detail.field}
        </p>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        <dt className="text-muted-foreground">Old value</dt>
        <dd className="tabular-nums">{detail.old_value ?? ""}</dd>
        <dt className="text-muted-foreground">{detail.action === "flag" ? "Note" : "New value"}</dt>
        <dd className="tabular-nums">{detail.new_value ?? ""}</dd>
        {detail.latest_decision?.edited_value ? (
          <>
            <dt className="text-muted-foreground">Edited value</dt>
            <dd className="tabular-nums">{detail.latest_decision.edited_value}</dd>
          </>
        ) : null}
      </dl>

      <section>
        <h3 className="font-semibold">Why</h3>
        <p className="mt-1">
          {detail.explanation
            ? fillEvidenceTokens(detail.explanation, detail.evidence.values)
            : detail.explanation === null
              ? "Explanation failed. Run again to write it."
              : "No explanation has been written yet."}
        </p>
      </section>

      <section>
        <h3 className="font-semibold">Evidence</h3>
        <p className="mt-1">{detail.evidence.summary}</p>
        {values.length > 0 ? (
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4">
            {values.map(([name, value]) => (
              <div key={name} className="contents">
                <dt className="text-muted-foreground">{sentenceCase(name)}</dt>
                <dd className="tabular-nums">{evidenceValueText(value)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {detail.evidence.record_keys.length > 0 ? (
          <div className="mt-2">
            <p className="text-muted-foreground">Linked records</p>
            <ul>
              {detail.evidence.record_keys.map((key) => (
                <li key={key}>{key}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <p className="mt-2 text-muted-foreground">{proposerLabel(detail.proposer)}</p>
      </section>

      {rule ? <BacktestNote rule={rule} /> : null}

      {detail.decisions.length > 0 ? (
        <section>
          <h3 className="font-semibold">Decisions</h3>
          <ul className="mt-1">
            {detail.decisions.map((decision) => (
              <li key={decision.decision_id}>
                {sentenceCase(decision.decision)} by {decision.reviewer},{" "}
                {dateAndTime(decision.decided_at)}
                {decision.comment ? `. ${decision.comment}` : ""}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {canDecide ? (
        <ProposalDecisionForm
          key={proposalId}
          proposal={detail}
          mode={mode}
          onMode={onMode}
          decide={decide}
          isPending={isPending}
          error={error}
        />
      ) : (
        <p className="text-muted-foreground">
          Only the data specialist records decisions on data fixes. Switch role to decide.
        </p>
      )}
    </div>
  );
}
