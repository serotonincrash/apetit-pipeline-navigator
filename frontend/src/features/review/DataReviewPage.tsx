import { useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useGetRun, useListProposals, useListRules } from "@/api/generated/client";
import type { Proposal } from "@/api/generated/model";
import { usePersona } from "@/api/persona";
import { useRecipe } from "@/api/recipe";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { TableSkeleton } from "@/components/TableSkeleton";
import { BacktestNote } from "@/features/review/BacktestNote";
import { BulkDecision } from "@/features/review/BulkDecision";
import { ProposalFilters } from "@/features/review/ProposalFilters";
import { ProposalPanel } from "@/features/review/ProposalPanel";
import { ProposalTable } from "@/features/review/ProposalTable";
import { groupByDataCheck, openFixIdsOf } from "@/features/review/proposalGroups";
import { RunAgainBar } from "@/features/review/RunAgainBar";
import { useProposalDecision } from "@/features/review/useProposalDecision";
import { sourceName } from "@/lib/labels";
import { checkedData } from "@/lib/recipes";

export interface ReviewSearch {
  rule?: string;
  table?: string;
  status?: string;
  selected?: string;
}

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable)
  );
}

export function DataReviewPage({ search }: { search: ReviewSearch }) {
  const navigate = useNavigate({ from: "/review/data" });
  const persona = usePersona();
  const canDecide = persona.role === "data_specialist";
  const recipe = useRecipe();
  const proposals = useListProposals({ limit: 2000, recipe_id: recipe });
  const rules = useListRules();
  const [mode, setMode] = useState<"reject" | "edit">();
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const runId = proposals.data?.run_id ?? "";
  const run = useGetRun(runId, { query: { enabled: runId !== "" } });

  const setSearch = useCallback(
    (next: ReviewSearch, replace = false) => void navigate({ search: next, replace }),
    [navigate],
  );

  const all = proposals.data?.items ?? [];
  const filtered = useMemo(
    () =>
      all.filter(
        (item) =>
          (!search.rule || item.rule_id === search.rule) &&
          (!search.table || item.table === search.table) &&
          (!search.status || item.status === search.status),
      ),
    [all, search.rule, search.table, search.status],
  );
  const groups = useMemo(() => groupByDataCheck(filtered), [filtered]);
  // The keys move through what is on screen, so a collapsed data check is skipped.
  const shown = groups.flatMap((group) => (collapsed.has(group.ruleId) ? [] : group.proposals));
  const selectedIndex = shown.findIndex((item) => item.proposal_id === search.selected);
  const selected: Proposal | undefined = shown[selectedIndex];
  const rule = rules.data?.find((item) => item.rule_id === (selected?.rule_id ?? search.rule));

  const decision = useProposalDecision(() => {
    setMode(undefined);
    const next = shown[selectedIndex + 1];
    if (next) setSearch({ ...search, selected: next.proposal_id }, true);
  });

  const openFixIds = openFixIdsOf(filtered);
  const openSources = groups
    .filter((group) => group.openFixIds.length > 0)
    .map((group) => sourceName(group.proposer));

  const toggleGroup = (ruleId: string) => {
    const next = new Set(collapsed);
    if (!next.delete(ruleId)) next.add(ruleId);
    setCollapsed(next);
  };

  const since = run.data?.finished_at ?? run.data?.created_at;
  const newDecisions = all.filter(
    (item) => item.latest_decision && since && item.latest_decision.decided_at > since,
  ).length;

  const move = useCallback(
    (step: number) => {
      const index = Math.min(Math.max(selectedIndex + step, 0), shown.length - 1);
      const target = shown[index];
      if (target) setSearch({ ...search, selected: target.proposal_id }, true);
    },
    [selectedIndex, shown, search, setSearch],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        move(1);
      } else if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        move(-1);
      } else if (selected && canDecide) {
        if (event.key === "a" && selected.action === "fix") {
          decision.decide(selected.proposal_id, "approve");
        } else if (event.key === "r") {
          event.preventDefault();
          setMode("reject");
        } else if (event.key === "e" && selected.action === "fix") {
          event.preventDefault();
          setMode("edit");
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [move, selected, canDecide, decision]);

  const options = useMemo(
    () => ({
      rules: [...new Set(all.map((item) => item.rule_id))].sort(),
      tables: [...new Set(all.map((item) => item.table))].sort(),
    }),
    [all],
  );

  return (
    <div className="flex min-h-screen">
      <main className="min-w-0 flex-1 px-6 py-6">
        <h1 className="text-lg font-semibold">Data review</h1>
        <div className="mt-3 space-y-3">
          <ProposalFilters
            options={options}
            rule={search.rule}
            table={search.table}
            status={search.status}
            onChange={(next) => setSearch({ ...next })}
          />
          {search.rule && rule && !selected ? <BacktestNote rule={rule} /> : null}
          {canDecide && openSources.length > 1 ? (
            <BulkDecision scope={`from ${openSources.join(", ")}`} openFixIds={openFixIds} />
          ) : null}
          {newDecisions > 0 ? <RunAgainBar decisions={newDecisions} runId={runId} /> : null}
          <p className="text-xs text-muted-foreground">
            Keys: j and k or the arrow keys move
            {canDecide ? ", a approves, e edits, r rejects" : ""}.
          </p>
        </div>

        <div className="mt-3">
          {proposals.isPending ? <TableSkeleton rows={12} /> : null}
          {proposals.isError ? (
            <ErrorState
              title="The suggested fixes did not load."
              message="Check that the server is running, then try again."
              onRetry={() => void proposals.refetch()}
            />
          ) : null}
          {proposals.data && all.length === 0 ? (
            <EmptyState title="No suggested fixes yet.">
              Start a run to check the {checkedData(recipe)}.
            </EmptyState>
          ) : null}
          {proposals.data && all.length > 0 && filtered.length === 0 ? (
            <EmptyState title="No suggested fixes match these filters.">
              Clear a filter to see more.
            </EmptyState>
          ) : null}
          {groups.length > 0 ? (
            <ProposalTable
              groups={groups}
              rules={rules.data ?? []}
              collapsed={collapsed}
              onToggle={toggleGroup}
              canDecide={canDecide}
              selectedId={search.selected}
              onSelect={(id) => setSearch({ ...search, selected: id }, true)}
            />
          ) : null}
        </div>
      </main>

      {selected ? (
        <aside className="w-full max-w-panel shrink-0 border-l" aria-label="Suggested fix">
          <ProposalPanel
            proposalId={selected.proposal_id}
            rule={rule}
            canDecide={canDecide}
            mode={mode}
            onMode={setMode}
            decide={decision.decide}
            isPending={decision.isPending}
            error={decision.error}
          />
        </aside>
      ) : null}
    </div>
  );
}
