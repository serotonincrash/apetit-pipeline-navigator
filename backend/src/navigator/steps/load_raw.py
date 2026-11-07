"""load_raw: reads the package files a recipe names into raw tables, unchanged.

The seed job records each source file and its checksum, so this step records nothing else.
"""

import io
from collections.abc import Mapping
from typing import Any, cast

import pandas as pd

from navigator.recipes.core import Artifact, Params, RunContext, StepResult, section, step


def read_table(path: str, content: bytes, read_options: Mapping[str, Any]) -> pd.DataFrame:
    """One package file as a table: Parquet by its extension, otherwise CSV."""
    if path.endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(content))
    return cast(pd.DataFrame, pd.read_csv(io.BytesIO(content), **read_options))


@step(
    "load_raw",
    kind="load",
    summary=(
        "Reads the files the recipe names from the challenge package, exactly as delivered, and "
        "keeps each as a raw table that later steps never change."
    ),
)
def load_raw(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult:
    files: Mapping[str, Mapping[str, Any]] = params["files"]
    tables: list[Artifact] = []
    with section(
        "read files",
        "Reads each file with the separator and decimal mark it was delivered with, such as "
        "the semicolons and decimal commas in the Foodhills file.",
    ):
        for name, entry in files.items():
            path: str = entry["path"]
            frame = read_table(path, ctx.sources[path].content, entry.get("read", {}))
            tables.append(Artifact(name=name, layer="raw", frame=frame))
    return StepResult(tables=tables)
