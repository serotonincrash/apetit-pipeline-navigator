import type { Assumption, RunRequestStepParams } from "@/api/generated/model";
import { REGION_CODES, regionLabel, transitionLabel } from "@/lib/labels";

const PRICE = "price_risk.contract_price_eur_t.";
const PREMIUM = "price_risk.replacement_premium.";
const LIFT = "price_risk.replacement_premium_lift";

/** One value a person can change before queuing a run. */
export interface EditableValue {
  id: string;
  label: string;
  unit: string;
  source: string;
  original: number;
  /** Where the value goes in the run's step params. */
  target:
    | { kind: "price"; item: string }
    | { kind: "premium"; item: string }
    | { kind: "lift"; ngfs: string };
}

/** Assumption labels carry region codes; show the region's name instead. */
export function assumptionLabel(label: string): string {
  let text = label;
  for (const code of REGION_CODES) {
    text = text.replace(new RegExp(`, ${code} (.+)$`), (_m, crop: string) => {
      return `, ${crop}, ${regionLabel(code)}`;
    });
  }
  return text.replace(/^./, (first) => first.toUpperCase());
}

export function editableValues(assumptions: Assumption[]): EditableValue[] {
  const found: EditableValue[] = [];
  for (const assumption of assumptions) {
    const { name, value } = assumption;
    const base = {
      unit: assumption.unit,
      source: assumption.source,
    };
    if (name.startsWith(PRICE) && typeof value === "number") {
      found.push({
        ...base,
        id: name,
        label: assumptionLabel(assumption.label),
        original: value,
        target: { kind: "price", item: name.slice(PRICE.length) },
      });
    } else if (name.startsWith(PREMIUM) && !name.startsWith(LIFT) && typeof value === "number") {
      found.push({
        ...base,
        id: name,
        label: assumptionLabel(assumption.label),
        original: value,
        target: { kind: "premium", item: name.slice(PREMIUM.length) },
      });
    } else if (name === LIFT && value !== null && typeof value === "object") {
      for (const [ngfs, lift] of Object.entries(value as Record<string, unknown>)) {
        if (typeof lift !== "number") continue;
        found.push({
          ...base,
          id: `${LIFT}.${ngfs}`,
          label: `Premium rise, ${transitionLabel(ngfs)}`,
          original: lift,
          target: { kind: "lift", ngfs },
        });
      }
    }
  }
  return found;
}

export function isEditableName(name: string): boolean {
  return (
    name.startsWith(PRICE) || (name.startsWith(PREMIUM) && !name.startsWith(LIFT)) || name === LIFT
  );
}

/** The step params for the values that changed, in the shape the price_risk step reads. */
export function stepParamsFor(
  editable: EditableValue[],
  drafts: Record<string, string>,
): { stepParams: RunRequestStepParams | undefined; changed: number } {
  const overrides: Record<string, Record<string, number>> = {};
  const lift: Record<string, number> = {};
  let changed = 0;
  for (const item of editable) {
    const draft = drafts[item.id];
    if (draft === undefined || draft.trim() === "") continue;
    const next = Number(draft);
    if (!Number.isFinite(next) || next === item.original) continue;
    changed += 1;
    const { target } = item;
    if (target.kind === "lift") {
      lift[target.ngfs] = next;
    } else {
      const entry = overrides[target.item] ?? {};
      entry[target.kind === "price" ? "contract_price_eur_t" : "replacement_import_premium_frac"] =
        next;
      overrides[target.item] = entry;
    }
  }
  const priceRisk: Record<string, unknown> = {};
  if (Object.keys(overrides).length > 0) priceRisk.price_overrides = overrides;
  if (Object.keys(lift).length > 0) priceRisk.replacement_premium_lift = lift;
  return {
    stepParams: changed > 0 ? { price_risk: priceRisk } : undefined,
    changed,
  };
}
