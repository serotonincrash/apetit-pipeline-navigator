"""Step: apply_approved. Placeholder until the step is refactored from the notebooks."""

from navigator.recipes.core import Artifact, Params, RunContext, StepResult, step


@step(
    "apply_approved",
    kind="transform",
    summary="Builds the cleaned farm survey, registry and Foodhills tables from the raw data plus the approved fixes.",
)
def apply_approved(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    raise NotImplementedError("apply_approved is not refactored yet")
