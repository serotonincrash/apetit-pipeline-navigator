import type { Rule } from "@/api/generated/model";
import { InfoTip } from "@/components/InfoTip";
import { count, share } from "@/lib/format";

interface BacktestField {
  key: string;
  label: string;
  kind: "share" | "count";
  tip?: string;
}

const FIELDS: BacktestField[] = [
  {
    key: "precision",
    label: "Precision",
    kind: "share",
    tip: "Of the records this check flagged in 2023 to 2024, the share that are known issues.",
  },
  {
    key: "recall",
    label: "Recall",
    kind: "share",
    tip: "Of the known issues in 2023 to 2024, the share this check flagged.",
  },
  {
    key: "dev_labels",
    label: "Known issues, 2023 to 2024",
    kind: "count",
    tip: "Records listed in the known data issues table for this check.",
  },
  { key: "dev_flagged", label: "Flagged records, 2023 to 2024", kind: "count" },
  { key: "flagged_all_years", label: "Flagged records, all seasons", kind: "count" },
  {
    key: "fixed_value_matches_truth",
    label: "Fixes that match the known value",
    kind: "share",
    tip: "Of the known issues this check fixed, the share whose new value equals the value in the known data issues table.",
  },
];

/** What the data check found, compared with known issues where those exist. */
export function BacktestNote({ rule }: { rule: Rule }) {
  const entries = FIELDS.flatMap((field) => {
    const value = rule.backtest[field.key];
    return typeof value === "number"
      ? [{ ...field, text: field.kind === "share" ? share(value) : count(value) }]
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
              <dt className="text-muted-foreground">
                {entry.label}
                {entry.tip ? <InfoTip term={entry.label}>{entry.tip}</InfoTip> : null}
              </dt>
              <dd className="tabular-nums">{entry.text}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {typeof rule.backtest.precision === "number" ? null : (
        <p className="mt-1 text-muted-foreground">
          No known issues exist for this check, so it has no precision or recall.
        </p>
      )}
    </div>
  );
}
