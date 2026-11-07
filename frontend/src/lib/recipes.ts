import type { Run } from "@/api/generated/model";
import { sentenceCase } from "@/lib/labels";

const RECIPES: Record<string, string> = {
  farm_climate_risk: "Farm climate risk",
  energy_meter_check: "Energy-meter check",
};

export function recipeLabel(run: Pick<Run, "recipe_id" | "kind">): string {
  const name = RECIPES[run.recipe_id] ?? sentenceCase(run.recipe_id);
  if (run.kind === "report") return `${name}, report draft`;
  if (run.kind === "what_if") return `${name}, what-if`;
  return name;
}
