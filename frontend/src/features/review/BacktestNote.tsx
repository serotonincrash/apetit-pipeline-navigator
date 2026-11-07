import type { Rule } from "@/api/generated/model";
import { count, share } from "@/lib/format";

const FIELDS: [string, string, "share" | "count"][] = [
  ["precision", "Precision", "share"],
  ["recall", "Recall", "share"],
  ["dev_labels", "Labelled records, 2023 to 2024", "count"],
  ["dev_flagged", "Flagged records, 2023 to 2024", "count"],
  ["flagged_all_years", "Flagged records, all seasons", "count"],
  ["fixed_value_matches_truth", "Fixes that match the answer key", "share"],
];

/** What the data check found against the labelled 2023 and 2024 history. */
export function BacktestNote({ rule }: { rule: Rule }) {
  const entries = FIELDS.flatMap(([key, label, kind]) => {
    const value = rule.backtest[key];
    return typeof value === "number"
      ? [{ key, label, text: kind === "share" ? share(value) : count(value) }]
      : [];
  });
  return (
    <div className="border-l-2 pl-3">
      <p className="font-medium">Data check {rule.rule_id}</p>
      <p className="text-muted-foreground">{rule.description}</p>
      {entries.length > 0 ? (
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-4">
          {entries.map((entry) => (
            <div key={entry.key} className="contents">
              <dt className="text-muted-foreground">{entry.label}</dt>
              <dd className="tabular-nums">{entry.text}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}
