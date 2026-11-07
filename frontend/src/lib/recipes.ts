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

/**
 * Whether the fix proposer's fixes reach the recipe's results. A run applies only the fixes it
 * proposed itself, so such a recipe's rerun must ask the fix proposer again.
 */
const FIXES_FEED_RESULTS: Record<RecipeId, boolean> = {
  farm_climate_risk: false,
  energy_meter_check: true,
};

export const fixProposerFeedsResults = (recipeId: string) =>
  isRecipeId(recipeId) && FIXES_FEED_RESULTS[recipeId];

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
