"""Step: spatial_join. Placeholder until the step is refactored from the notebooks."""

from navigator.recipes.core import Artifact, Params, RunContext, StepResult, step


@step(
    "spatial_join",
    kind="transform",
    summary="Matches every parcel to its nearest weather cell and builds the parcel-year and farm-year tables.",
)
def spatial_join(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    raise NotImplementedError("spatial_join is not refactored yet")
