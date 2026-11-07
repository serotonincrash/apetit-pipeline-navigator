"""Step: load_raw. Placeholder until the step is refactored from the notebooks."""

from navigator.recipes.core import Artifact, Params, RunContext, StepResult, step


@step(
    "load_raw",
    kind="load",
    summary="Reads the challenge package files the recipe uses and stores each as a raw table.",
)
def load_raw(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    raise NotImplementedError("load_raw is not refactored yet")
