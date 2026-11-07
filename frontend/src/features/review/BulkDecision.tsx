import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useDecideProposals } from "@/api/generated/client";
import { requireName } from "@/api/persona";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { messageOf } from "@/lib/errors";
import { count } from "@/lib/format";

interface BulkDecisionProps {
  /** Where the fixes come from, as the end of a sentence: "from data check R1". */
  scope: string;
  openFixIds: string[];
}

/** Approve or reject a batch of open fixes, after a confirmation on the page. */
export function BulkDecision({ scope, openFixIds }: BulkDecisionProps) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState<"approve" | "reject">();
  const [comment, setComment] = useState("");
  const decide = useDecideProposals({
    mutation: {
      onSuccess: () => {
        // Covers the list and any open detail panel, whose keys share this prefix.
        void queryClient.invalidateQueries({
          predicate: (query) => String(query.queryKey[0]).startsWith("/api/proposals"),
        });
        setAsking(undefined);
        setComment("");
      },
    },
  });
  const number = count(openFixIds.length);
  const fixes = `${number} open ${openFixIds.length === 1 ? "fix" : "fixes"}`;
  if (openFixIds.length === 0) return null;

  if (!asking) {
    return (
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={() => {
            if (requireName()) setAsking("approve");
          }}
        >
          {openFixIds.length === 1 ? "Approve" : "Approve all"} {fixes}
        </Button>
        <Button
          size="sm"
          onClick={() => {
            if (requireName()) setAsking("reject");
          }}
        >
          {openFixIds.length === 1 ? "Reject" : "Reject all"} {fixes}
        </Button>
      </div>
    );
  }

  return (
    <div
      className="w-full space-y-2 border bg-background p-3"
      role="alertdialog"
      aria-label="Confirm decision"
    >
      <p className="font-medium">
        {asking === "approve" ? "Approve" : "Reject"} {fixes} {scope}? This records one decision for
        each fix.
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
          {asking === "approve" ? `Approve ${fixes}` : `Reject ${fixes}`}
        </Button>
        <Button variant="ghost" onClick={() => setAsking(undefined)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
