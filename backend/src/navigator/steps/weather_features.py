"""Step: weather_features. Placeholder until the step is refactored from the notebooks."""

from navigator.recipes.core import Artifact, Params, RunContext, StepResult, step


@step(
    "weather_features",
    kind="transform",
    summary="Computes drought, heat and rain measures for every cell, soil, crop, year and climate scenario with the tuned crop calendar.",
)
def weather_features(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    raise NotImplementedError("weather_features is not refactored yet")
