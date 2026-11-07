"""The recipes the platform can run. Importing the steps package registers every step."""

import navigator.steps  # noqa: F401  # pyright: ignore[reportUnusedImport]  (registers the steps)
from navigator.recipes import energy_meter_check, farm_climate_risk
from navigator.recipes.core import STEPS, Recipe

RECIPES: dict[str, Recipe] = {
    r.recipe_id: r for r in [farm_climate_risk.RECIPE, energy_meter_check.RECIPE]
}


def get_recipe(recipe_id: str) -> Recipe:
    recipe = RECIPES[recipe_id]
    missing = [s.name for s in recipe.steps if s.name not in STEPS]
    if missing:
        raise KeyError(f"recipe {recipe_id} uses unregistered steps: {missing}")
    return recipe
