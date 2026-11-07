import { useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useCreateRun, useListAssumptions } from "@/api/generated/client";
import { requireName } from "@/api/persona";
import { ErrorState } from "@/components/ErrorState";
import { SidePanel } from "@/components/SidePanel";
import { TableSkeleton } from "@/components/TableSkeleton";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { AssumptionField } from "@/features/risk/AssumptionField";
import {
  assumptionLabel,
  editableValues,
  isEditableName,
  stepParamsFor,
} from "@/lib/assumptionOverrides";
import { assumptionValue } from "@/lib/assumptions";
import { messageOf } from "@/lib/errors";
import { stepLabel } from "@/lib/labels";

interface AssumptionsPanelProps {
  resultSetId: string;
  onClose: () => void;
}

export function AssumptionsPanel({ resultSetId, onClose }: AssumptionsPanelProps) {
  const navigate = useNavigate();
  const assumptions = useListAssumptions({ result_set_id: resultSetId });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const start = useCreateRun({
    mutation: {
      onSuccess: (run) => void navigate({ to: "/runs/$runId", params: { runId: run.run_id } }),
    },
  });

  const editable = useMemo(() => editableValues(assumptions.data ?? []), [assumptions.data]);
  const { stepParams, changed } = stepParamsFor(editable, drafts);

  const fixed = (assumptions.data ?? []).filter((item) => !isEditableName(item.name));
  const steps = [...new Set(fixed.map((item) => item.step))];

  return (
    <SidePanel title="Assumptions" onClose={onClose}>
      <div className="space-y-6 p-4">
        {assumptions.isPending ? <TableSkeleton rows={10} /> : null}
        {assumptions.isError ? (
          <ErrorState
            title="The assumptions did not load."
            message="Close the panel and open it again."
            onRetry={() => void assumptions.refetch()}
          />
        ) : null}

        {editable.length > 0 ? (
          <section>
            <h3 className="font-semibold">Prices and premiums you can change</h3>
            <p className="mb-2 text-muted-foreground">
              Saving starts a new run with the values you changed.
            </p>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Assumption</TableHeaderCell>
                  <TableHeaderCell numeric>Value</TableHeaderCell>
                  <TableHeaderCell>Unit</TableHeaderCell>
                  <TableHeaderCell>Source</TableHeaderCell>
                </tr>
              </TableHead>
              <TableBody>
                {editable.map((item) => (
                  <AssumptionField
                    key={item.id}
                    item={item}
                    draft={drafts[item.id]}
                    onChange={(id, value) => setDrafts({ ...drafts, [id]: value })}
                  />
                ))}
              </TableBody>
            </Table>
            {changed > 0 ? (
              <div className="mt-3 flex items-center gap-3">
                <Button
                  variant="primary"
                  disabled={start.isPending}
                  onClick={() => {
                    if (requireName() && stepParams) {
                      start.mutate({
                        data: { recipe_id: "farm_climate_risk", step_params: stepParams },
                      });
                    }
                  }}
                >
                  Save and start a run
                </Button>
                <span className="text-muted-foreground">
                  {changed} {changed === 1 ? "value" : "values"} changed
                </span>
              </div>
            ) : null}
            {start.isError ? (
              <ErrorState title="The run did not start." message={messageOf(start.error)} />
            ) : null}
          </section>
        ) : null}

        {steps.map((step) => (
          <section key={step}>
            <h3 className="mb-1 font-semibold">{stepLabel(step)}</h3>
            <Table>
              <TableBody>
                {fixed
                  .filter((item) => item.step === step)
                  .map((item) => (
                    <TableRow key={item.assumption_id}>
                      <TableCell>{assumptionLabel(item.label)}</TableCell>
                      <TableCell numeric>{assumptionValue(item.value)}</TableCell>
                      <TableCell>{item.unit}</TableCell>
                      <TableCell className="text-muted-foreground">{item.source}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </section>
        ))}
      </div>
    </SidePanel>
  );
}
