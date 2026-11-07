"""Shared fixtures for golden tests: the challenge package read from disk, as the runner would
serve it from object storage, and steps 1 to 4 chained the way the runner chains them."""

import hashlib
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from navigator.recipes.core import (
    PROPOSALS_INPUT,
    Artifact,
    RunContext,
    SourceFile,
    StepFunction,
    StepResult,
    StepSpec,
)
from navigator.recipes.farm_climate_risk import RECIPE
from navigator.steps.apply_approved import apply_approved
from navigator.steps.check_farm_data import check_farm_data
from navigator.steps.load_raw import load_raw
from navigator.steps.spatial_join import spatial_join


class DiskPackage(Mapping[str, SourceFile]):
    def __init__(self, root: Path) -> None:
        self.root = root

    def __getitem__(self, path: str) -> SourceFile:
        content = (self.root / path).read_bytes()
        return SourceFile(path=path, sha256=hashlib.sha256(content).hexdigest(), content=content)

    def __iter__(self) -> Iterator[str]:
        return (str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())

    def __len__(self) -> int:
        return sum(1 for _ in self)


@pytest.fixture(scope="session")
def package_root() -> Path:
    root = Path(os.environ.get("PACKAGE_DIR", "../APETIT_CLIMATE_NATURE_NAVIGATOR_2026")).resolve()
    if not (root / "data").exists():
        pytest.skip(f"challenge package not found at {root}; set PACKAGE_DIR")
    return root


@pytest.fixture(scope="session")
def ctx(package_root: Path) -> RunContext:
    return RunContext(
        run_id="run_golden", recipe_id="farm_climate_risk", sources=DiskPackage(package_root)
    )


def recipe_step(name: str) -> StepSpec:
    return next(spec for spec in RECIPE.steps if spec.name == name)


def run_step(
    ctx: RunContext, func: StepFunction, name: str, tables: Mapping[str, Artifact]
) -> StepResult:
    """One step with its recipe params and the inputs the recipe names, as the runner calls it."""
    spec = recipe_step(name)
    return func(ctx, {n: tables[n] for n in spec.inputs}, spec.params)


def _as_text(value: Any) -> Any:
    """Proposal values as the runner stores them: text, with missing values left empty."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return value if isinstance(value, str) else str(value)


def proposals_input(check: StepResult) -> pd.DataFrame:
    """The `proposals` input the runner builds after a reviewer has approved the fixes of rules
    R1, R2, R3 and R5: those fixes are approved, flags stay flags, the rest are open."""
    assert check.proposals is not None
    proposals = check.proposals
    columns = [
        "proposal_key",
        "rule_id",
        "issue_type",
        "table",
        "record_key",
        "field",
        "old_value",
        "new_value",
        "action",
    ]
    frame = pd.DataFrame({c: [_as_text(v) for v in proposals[c]] for c in columns})
    approved = proposals["rule_id"].isin(["R1", "R2", "R3", "R5"])
    frame["status"] = np.where(
        proposals["action"].eq("flag"), "flag", np.where(approved, "approved", "open")
    )
    return frame


@pytest.fixture(scope="session")
def raw_tables(ctx: RunContext) -> dict[str, Artifact]:
    loaded = run_step(ctx, load_raw, "load_raw", {})
    return {table.name: table for table in loaded.tables}


@pytest.fixture(scope="session")
def farm_checks(ctx: RunContext, raw_tables: dict[str, Artifact]) -> StepResult:
    return run_step(ctx, check_farm_data, "check_farm_data", raw_tables)


@pytest.fixture(scope="session")
def clean_tables(
    ctx: RunContext, raw_tables: dict[str, Artifact], farm_checks: StepResult
) -> dict[str, Artifact]:
    """Every table steps 1 to 4 write, plus the `proposals` input, by name."""
    tables = dict(raw_tables)
    tables.update({table.name: table for table in farm_checks.tables})
    tables[PROPOSALS_INPUT] = Artifact(
        name=PROPOSALS_INPUT, layer="result", frame=proposals_input(farm_checks)
    )
    for func, name in ((apply_approved, "apply_approved"), (spatial_join, "spatial_join")):
        result = run_step(ctx, func, name, tables)
        tables.update({table.name: table for table in result.tables})
    return tables
