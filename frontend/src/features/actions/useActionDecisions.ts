import { useQueryClient } from "@tanstack/react-query";
import {
  getListActionOptionsQueryKey,
  getListActionsQueryKey,
  useDecideAction,
  useDecideActionOption,
} from "@/api/generated/client";
import type {
  ActionDecisionRequestDecision,
  ActionOptionDecisionRequestDecision,
} from "@/api/generated/model";
import { requireName } from "@/api/persona";

/** Approve or reject a proposed action. */
export function useActionDecision() {
  const queryClient = useQueryClient();
  const mutation = useDecideAction({
    mutation: {
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: getListActionsQueryKey() }),
    },
  });
  const decide = (actionId: string, decision: ActionDecisionRequestDecision) => {
    if (requireName()) mutation.mutate({ actionId, data: { decision } });
  };
  return { decide, isPending: mutation.isPending, error: mutation.error };
}

/** Mark a priced option recommended, considered or rejected, with a comment. */
export function useActionOptionDecision(resultSetId: string, onSaved: () => void) {
  const queryClient = useQueryClient();
  const mutation = useDecideActionOption({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: getListActionOptionsQueryKey(resultSetId),
        });
        onSaved();
      },
    },
  });
  const decide = (
    optionId: string,
    decision: ActionOptionDecisionRequestDecision,
    comment: string,
  ) => {
    if (requireName()) mutation.mutate({ optionId, data: { decision, comment: comment.trim() } });
  };
  return { decide, isPending: mutation.isPending, error: mutation.error };
}
