import { useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import {
  useGetRun,
  useListActionOptions,
  useListActions,
  useListAssumptions,
  useListMetrics,
  useListResultSets,
} from "@/api/generated/client";
import { usePersona } from "@/api/persona";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { TableSkeleton } from "@/components/TableSkeleton";
import { ActionFilters } from "@/features/actions/ActionFilters";
import { ActionOptionsTable } from "@/features/actions/ActionOptionsTable";
import { ProposedActions } from "@/features/actions/ProposedActions";
import { RefusedActions } from "@/features/actions/RefusedActions";

export interface ActionsSearch {
  set?: string;
  scenario?: string;
}

const DEFAULT_SCENARIO = "ssp245";

export function ActionsPage({ search }: { search: ActionsSearch }) {
  const navigate = useNavigate({ from: "/actions" });
  const canDecide = usePersona().role === "sustainability_specialist";
  const scenario = search.scenario ?? DEFAULT_SCENARIO;
  const resultSets = useListResultSets();
  const ordered = useMemo(
    () => [...(resultSets.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [resultSets.data],
  );
  const resultSet = ordered.find((item) => item.result_set_id === search.set) ?? ordered[0];
  const resultSetId = resultSet?.result_set_id ?? "";
  const enabled = resultSetId !== "";
  const query = { query: { enabled } };

  const options = useListActionOptions(resultSetId, query);
  const actions = useListActions(undefined);
  const assumptions = useListAssumptions({ result_set_id: resultSetId }, query);
  const metricParams = (name: string) => ({ name, scenario, limit: 500 });
  const riskRemoved = useListMetrics(
    resultSetId,
    metricParams("compare_actions.risk_removed_eur"),
    query,
  );
  const emissionsRemoved = useListMetrics(
    resultSetId,
    metricParams("compare_actions.import_tco2e_removed"),
    query,
  );
  const run = useGetRun(resultSet?.run_id ?? "", { query: { enabled } });

  const shown = (options.data ?? []).filter((option) => option.scenario === scenario);
  const refusedArtifact = run.data?.artifacts.find((item) => item.name === "actions_not_run");
  const failed = options.isError || riskRemoved.isError || emissionsRemoved.isError;
  const loading = options.isPending || riskRemoved.isPending || emissionsRemoved.isPending;

  return (
    <main className="space-y-5 px-6 py-6">
      <h1 className="text-lg font-semibold">Actions</h1>
      {canDecide ? null : (
        <p className="text-muted-foreground">
          Only the sustainability specialist approves actions and marks options. Switch role to
          decide.
        </p>
      )}

      <section className="space-y-2">
        <h2 className="font-semibold">Proposed actions</h2>
        <ProposedActions canDecide={canDecide} />
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Priced options</h2>
        {resultSets.isPending ? <TableSkeleton rows={6} /> : null}
        {resultSets.isError ? (
          <ErrorState
            title="The results did not load."
            message="Check that the server is running, then try again."
            onRetry={() => void resultSets.refetch()}
          />
        ) : null}
        {resultSets.data && ordered.length === 0 ? (
          <EmptyState title="No priced options yet. Review the fixes and run again." />
        ) : null}
        {enabled ? (
          <>
            <ActionFilters
              resultSets={ordered}
              resultSetId={resultSetId}
              scenario={scenario}
              onResultSet={(id) => void navigate({ search: { ...search, set: id }, replace: true })}
              onScenario={(next) =>
                void navigate({ search: { ...search, scenario: next }, replace: true })
              }
            />
            {loading ? <TableSkeleton rows={5} /> : null}
            {failed ? (
              <ErrorState
                title="The priced options did not load."
                message="Try again, or pick other results."
                runId={resultSet?.run_id}
                onRetry={() => {
                  void options.refetch();
                  void riskRemoved.refetch();
                  void emissionsRemoved.refetch();
                }}
              />
            ) : null}
            {!loading && !failed && shown.length === 0 ? (
              <EmptyState title="No actions were priced for this climate scenario.">
                Pick another scenario, or approve actions and run again.
              </EmptyState>
            ) : null}
            {!loading && !failed && shown.length > 0 ? (
              <ActionOptionsTable
                options={shown}
                actions={actions.data ?? []}
                assumptions={assumptions.data ?? []}
                riskRemoved={riskRemoved.data?.items ?? []}
                emissionsRemoved={emissionsRemoved.data?.items ?? []}
                resultSetId={resultSetId}
                canDecide={canDecide}
              />
            ) : null}
          </>
        ) : null}
      </section>

      {refusedArtifact && refusedArtifact.row_count > 0 ? (
        <section className="space-y-2">
          <h2 className="font-semibold">Actions that were not priced</h2>
          <RefusedActions artifactId={refusedArtifact.artifact_id} />
        </section>
      ) : null}
    </main>
  );
}
