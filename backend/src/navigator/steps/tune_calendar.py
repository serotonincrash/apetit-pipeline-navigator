"""Step: tune_calendar. Placeholder until the step is refactored from the notebooks."""

from navigator.recipes.core import Artifact, Params, RunContext, StepResult, step


@step(
    "tune_calendar",
    kind="model",
    summary="Picks the sowing temperature and maturity length for each region and crop, so the modelled harvest lands inside the delivery dates in the ERP data.",
)
def tune_calendar(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    raise NotImplementedError("tune_calendar is not refactored yet")
