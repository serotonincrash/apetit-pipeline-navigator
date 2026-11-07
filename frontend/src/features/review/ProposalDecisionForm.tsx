import { useState } from "react";
import type { ProposalDetail } from "@/api/generated/model";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { Decide } from "@/features/review/useProposalDecision";
import { messageOf } from "@/lib/errors";

interface ProposalDecisionFormProps {
  proposal: ProposalDetail;
  mode: "reject" | "edit" | undefined;
  onMode: (mode: "reject" | "edit" | undefined) => void;
  decide: Decide;
  isPending: boolean;
  error: unknown;
}

function KeyHint({ children }: { children: string }) {
  return <kbd className="ml-1 border px-1 text-xs text-muted-foreground">{children}</kbd>;
}

/** Approve, edit or reject one suggested fix. Flags can only be rejected. */
export function ProposalDecisionForm({
  proposal,
  mode,
  onMode,
  decide,
  isPending,
  error,
}: ProposalDecisionFormProps) {
  const [comment, setComment] = useState("");
  const [edited, setEdited] = useState(proposal.new_value ?? "");
  const isFlag = proposal.action === "flag";

  const send = (decision: "approve" | "edit" | "reject") => {
    decide(proposal.proposal_id, decision, { comment, editedValue: edited });
    setComment("");
    onMode(undefined);
  };

  return (
    <section className="space-y-3 border-t pt-4">
      {error ? <ErrorState title="The decision was not saved." message={messageOf(error)} /> : null}

      {mode === "reject" ? (
        <div className="space-y-2">
          <label className="block">
            <span className="font-medium">Why reject this {isFlag ? "flag" : "fix"}</span>
            <Textarea
              autoFocus
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.stopPropagation();
                  onMode(undefined);
                }
              }}
            />
          </label>
          <div className="flex gap-2">
            <Button
              variant="danger"
              disabled={!comment.trim() || isPending}
              onClick={() => send("reject")}
            >
              Reject {isFlag ? "flag" : "fix"}
            </Button>
            <Button variant="ghost" onClick={() => onMode(undefined)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {mode === "edit" && !isFlag ? (
        <div className="space-y-2">
          <label className="block">
            <span className="font-medium">Edited value</span>
            <Input
              autoFocus
              value={edited}
              onChange={(event) => setEdited(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.stopPropagation();
                  onMode(undefined);
                }
              }}
            />
          </label>
          <label className="block">
            <span className="font-medium">Comment</span>
            <Textarea value={comment} onChange={(event) => setComment(event.target.value)} />
          </label>
          <div className="flex gap-2">
            <Button
              variant="primary"
              disabled={!edited.trim() || isPending}
              onClick={() => send("edit")}
            >
              Save edited fix
            </Button>
            <Button variant="ghost" onClick={() => onMode(undefined)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {mode === undefined ? (
        <div className="flex flex-wrap items-center gap-2">
          {isFlag ? null : (
            <>
              <Button variant="primary" disabled={isPending} onClick={() => send("approve")}>
                Approve fix
                <KeyHint>a</KeyHint>
              </Button>
              <Button onClick={() => onMode("edit")}>
                Edit value
                <KeyHint>e</KeyHint>
              </Button>
            </>
          )}
          <Button onClick={() => onMode("reject")}>
            Reject {isFlag ? "flag" : "fix"}
            <KeyHint>r</KeyHint>
          </Button>
        </div>
      ) : null}
    </section>
  );
}
