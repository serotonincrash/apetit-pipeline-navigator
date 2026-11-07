import { useQueryClient } from "@tanstack/react-query";
import { getListProposalsQueryKey, useDecideProposal } from "@/api/generated/client";
import { requireName } from "@/api/persona";

export type Decide = (
  proposalId: string,
  decision: "approve" | "edit" | "reject",
  options?: { comment?: string; editedValue?: string },
) => void;

/** One place that records a decision on one proposal, for the buttons and the keys. */
export function useProposalDecision(onSaved: () => void) {
  const queryClient = useQueryClient();
  const mutation = useDecideProposal({
    mutation: {
      onSuccess: (_decision, variables) => {
        void queryClient.invalidateQueries({ queryKey: getListProposalsQueryKey() });
        void queryClient.invalidateQueries({
          queryKey: [`/api/proposals/${variables.proposalId}`],
        });
        onSaved();
      },
    },
  });

  const decide: Decide = (proposalId, decision, options) => {
    if (!requireName()) return;
    mutation.mutate({
      proposalId,
      data: {
        decision,
        comment: options?.comment?.trim() || null,
        edited_value: decision === "edit" ? (options?.editedValue ?? null) : null,
      },
    });
  };

  return { decide, isPending: mutation.isPending, error: mutation.error };
}
