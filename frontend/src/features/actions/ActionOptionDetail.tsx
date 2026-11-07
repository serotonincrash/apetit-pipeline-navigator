import { useState } from "react";
import type { Action, ActionOption, Assumption } from "@/api/generated/model";
import { AssumptionsList } from "@/components/AssumptionsList";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useActionOptionDecision } from "@/features/actions/useActionDecisions";
import { messageOf } from "@/lib/errors";

interface ActionOptionDetailProps {
  option: ActionOption;
  action: Action | undefined;
  assumptions: Assumption[];
  resultSetId: string;
  canDecide: boolean;
}

function costSource(action: Action | undefined): string {
  const source = action?.cost.source;
  return typeof source === "string" ? source : "";
}

/** The assumptions behind one option, and the form that marks it. */
export function ActionOptionDetail({
  option,
  action,
  assumptions,
  resultSetId,
  canDecide,
}: ActionOptionDetailProps) {
  const [comment, setComment] = useState("");
  const decision = useActionOptionDecision(resultSetId, () => setComment(""));
  const behind = assumptions.filter((item) => option.assumption_ids.includes(item.assumption_id));
  const mark = (value: "recommended" | "considered" | "rejected") =>
    decision.decide(option.option_id, value, comment);

  return (
    <div className="space-y-4 p-3">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        <dt className="text-muted-foreground">Driver</dt>
        <dd>{action?.driver}</dd>
        <dt className="text-muted-foreground">Cost source</dt>
        <dd>{costSource(action)}</dd>
        <dt className="text-muted-foreground">Confidence</dt>
        <dd>{option.confidence}</dd>
      </dl>

      <section>
        <h3 className="font-semibold">Assumptions behind this option</h3>
        <div className="mt-1 max-h-80 overflow-y-auto border">
          <AssumptionsList assumptions={behind} />
        </div>
      </section>

      {canDecide ? (
        <section className="space-y-2 border-t pt-3">
          {decision.error ? (
            <ErrorState title="The mark was not saved." message={messageOf(decision.error)} />
          ) : null}
          <label className="block">
            <span className="font-medium">Comment</span>
            <Textarea value={comment} onChange={(event) => setComment(event.target.value)} />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              disabled={!comment.trim() || decision.isPending}
              onClick={() => mark("recommended")}
            >
              Mark recommended
            </Button>
            <Button
              disabled={!comment.trim() || decision.isPending}
              onClick={() => mark("considered")}
            >
              Mark considered
            </Button>
            <Button
              disabled={!comment.trim() || decision.isPending}
              onClick={() => mark("rejected")}
            >
              Mark rejected
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
