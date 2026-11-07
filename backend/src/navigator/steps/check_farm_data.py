"""Step: check_farm_data. Placeholder until the step is refactored from the notebooks."""

from navigator.recipes.core import Artifact, Params, RunContext, StepResult, step


@step(
    "check_farm_data",
    kind="propose",
    summary="Checks the farm survey and registry with rules R1 to R5 and proposes fixes or flags for what looks wrong.",
)
def check_farm_data(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    raise NotImplementedError("check_farm_data is not refactored yet")
