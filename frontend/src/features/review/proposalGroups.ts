import type { Proposal } from "@/api/generated/model";

export interface ProposalGroup {
  ruleId: string;
  proposer: string;
  proposals: Proposal[];
  openFixIds: string[];
}

export function openFixIdsOf(proposals: Proposal[]): string[] {
  return proposals
    .filter((item) => item.action === "fix" && item.status === "open")
    .map((item) => item.proposal_id);
}

/** Splits proposals by the data check that raised them, keeping their order inside each check. */
export function groupByDataCheck(proposals: Proposal[]): ProposalGroup[] {
  const byRule = new Map<string, Proposal[]>();
  for (const proposal of proposals) {
    const known = byRule.get(proposal.rule_id);
    if (known) known.push(proposal);
    else byRule.set(proposal.rule_id, [proposal]);
  }
  return [...byRule]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([ruleId, items]) => ({
      ruleId,
      proposer: items[0]?.proposer ?? "",
      proposals: items,
      openFixIds: openFixIdsOf(items),
    }));
}
