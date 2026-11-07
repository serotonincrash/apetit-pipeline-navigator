import type { Run } from "@/api/generated/model";
import { sentenceCase } from "@/lib/labels";

export const RECIPE_IDS = ["farm_climate_risk", "energy_meter_check"] as const;
export type RecipeId = (typeof RECIPE_IDS)[number];

export const DEFAULT_RECIPE: RecipeId = "farm_climate_risk";

const RECIPES: Record<RecipeId, string> = {
  farm_climate_risk: "Farm climate risk",
  energy_meter_check: "Energy-meter check",
};

/** What the recipe checks, for empty states such as "Start a run to check the farm data." */
const CHECKED_DATA: Record<RecipeId, string> = {
  farm_climate_risk: "farm data",
  energy_meter_check: "meter readings",
};

export function isRecipeId(value: unknown): value is RecipeId {
  return RECIPE_IDS.some((id) => id === value);
}

export const checkedData = (recipe: RecipeId) => CHECKED_DATA[recipe];

export function recipeName(recipeId: string): string {
  return isRecipeId(recipeId) ? RECIPES[recipeId] : sentenceCase(recipeId);
}

export function recipeLabel(run: Pick<Run, "recipe_id" | "kind">): string {
  const name = recipeName(run.recipe_id);
  if (run.kind === "report") return `${name}, report draft`;
  if (run.kind === "what_if") return `${name}, what-if`;
  return name;
}
