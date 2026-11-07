import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getListProposalsQueryKey, useDecideProposals } from "@/api/generated/client";
import { requireName } from "@/api/persona";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { messageOf } from "@/lib/errors";
import { count } from "@/lib/format";

interface BulkDecisionProps {
  ruleId: string;
  openFixIds: string[];
}

/** Approve or reject all open fixes of one data check, after a confirmation on the page. */
export function BulkDecision({ ruleId, openFixIds }: BulkDecisionProps) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState<"approve" | "reject">();
  const [comment, setComment] = useState("");
  const decide = useDecideProposals({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getListProposalsQueryKey() });
        setAsking(undefined);
        setComment("");
      },
    },
  });
  const number = count(openFixIds.length);
  if (openFixIds.length === 0) return null;

  if (!asking) {
    return (
      <div className="flex items-center gap-2">
        <Button
          onClick={() => {
            if (requireName()) setAsking("approve");
          }}
        >
          Approve all {number} open fixes
        </Button>
        <Button
          onClick={() => {
            if (requireName()) setAsking("reject");
          }}
        >
          Reject all {number} open fixes
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-2 border p-3" role="alertdialog" aria-label="Confirm decision">
      <p className="font-medium">
        {asking === "approve" ? "Approve" : "Reject"} {number} open fixes from data check {ruleId}?
        This records one decision for each fix.
      </p>
      {asking === "reject" ? (
        <label className="block">
          <span>Why reject these fixes</span>
          <Textarea
            autoFocus
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
        </label>
      ) : null}
      {decide.isError ? (
        <ErrorState title="The decisions were not saved." message={messageOf(decide.error)} />
      ) : null}
      <div className="flex gap-2">
        <Button
          variant={asking === "approve" ? "primary" : "danger"}
          disabled={decide.isPending || (asking === "reject" && !comment.trim())}
          onClick={() =>
            decide.mutate({
              data: {
                proposal_ids: openFixIds,
                decision: asking,
                comment: comment.trim() || null,
              },
            })
          }
        >
          {asking === "approve" ? `Approve ${number} fixes` : `Reject ${number} fixes`}
        </Button>
        <Button variant="ghost" onClick={() => setAsking(undefined)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
