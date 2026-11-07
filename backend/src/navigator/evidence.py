"""Evidence queries: how a proposal's numbers can be recomputed from the raw tables.

A query is one of two kinds:

- `rule`: the proposal came from a rule we wrote. Recomputing it means running that rule again
  with the same params, so the query only names them.
- `compute`: the proposal came from an agent. The query is a fixed structure the runner
  evaluates with its own code: read a raw table, optionally join another on key columns,
  compute named values per row (aggregates within groups, then arithmetic), and keep the rows
  matching a filter. Nothing in it is free text, so the same data always gives the same numbers.

The runner evaluates a `compute` query and rejects the proposal when the result does not match
the `values` the agent claimed.
"""

from typing import Annotated, Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

AGGREGATES = ("median", "mean", "sum", "count", "min", "max")
ARITHMETIC = ("add", "subtract", "multiply", "divide")

# A filter value: one value, a list of values (any of them), or an inclusive range.
FilterValue = str | int | float | bool | list[str | int | float] | dict[str, float]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleQuery(_Model):
    kind: Literal["rule"]
    rule_id: str
    params: dict[str, Any] = Field(default_factory=dict[str, Any])
    group: dict[str, Any] | None = Field(
        default=None, description="The group the record was compared within, if any."
    )


class Aggregate(_Model):
    """A value computed over each row's group, for example the median yield per crop and year."""

    op: Literal["median", "mean", "sum", "count", "min", "max"]
    column: str


class Arithmetic(_Model):
    """A value computed per row from two columns, computed values or numbers."""

    op: Literal["add", "subtract", "multiply", "divide"]
    left: str | float
    right: str | float


class Join(_Model):
    table: str
    on: list[str] = Field(min_length=1)


class ComputeQuery(_Model):
    kind: Literal["compute"]
    table: str
    join: list[Join] = Field(default_factory=list[Join])
    group_by: list[str] = Field(default_factory=list[str])
    compute: dict[str, Aggregate | Arithmetic] = Field(min_length=1)
    where: dict[str, FilterValue] = Field(default_factory=dict[str, FilterValue])


EvidenceQuery = Annotated[RuleQuery | ComputeQuery, Field(discriminator="kind")]


class Evidence(_Model):
    summary: str = Field(description="One line of plain text saying why the proposal was made.")
    record_keys: list[str] = Field(min_length=1, description="The records the proposal rests on.")
    query: EvidenceQuery = Field(description="How to recompute the values from the raw tables.")
    values: dict[str, float] = Field(description="Named numbers the explanation cites.")


def _operand(frame: pd.DataFrame, operand: str | float) -> pd.Series | float:
    if isinstance(operand, str):
        if operand not in frame.columns:
            raise ValueError(f"The query refers to {operand!r}, which is not a column or value.")
        return pd.to_numeric(frame[operand], errors="coerce")
    return float(operand)


def apply_filter(frame: pd.DataFrame, where: dict[str, FilterValue]) -> pd.DataFrame:
    """Rows matching every key, as in a metric's lineage filter."""
    keep = pd.Series(True, index=frame.index)
    for column, value in where.items():
        if column not in frame.columns:
            raise ValueError(f"The query filters on {column!r}, which the table does not have.")
        if isinstance(value, list):
            keep &= frame[column].isin(value)
        elif isinstance(value, dict):
            if "min" in value:
                keep &= frame[column] >= value["min"]
            if "max" in value:
                keep &= frame[column] <= value["max"]
        else:
            keep &= frame[column] == value
    return frame[keep]


def evaluate(query: ComputeQuery, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The matching rows with every computed value as a column, in the order they were named."""
    if query.table not in tables:
        raise ValueError(f"The query reads {query.table!r}, which is not a raw table.")
    frame = tables[query.table].copy()
    for join in query.join:
        if join.table not in tables:
            raise ValueError(f"The query joins {join.table!r}, which is not a raw table.")
        frame = frame.merge(tables[join.table], on=join.on, how="left", suffixes=("", "_joined"))
    for name, step in query.compute.items():
        if isinstance(step, Aggregate):
            if step.column not in frame.columns:
                raise ValueError(f"The query aggregates {step.column!r}, which is not a column.")
            values = pd.to_numeric(frame[step.column], errors="coerce")
            if query.group_by:
                groups = [frame[c] for c in query.group_by]
                frame[name] = values.groupby(groups).transform(step.op)
            else:
                frame[name] = getattr(values, step.op)()
        else:
            left, right = _operand(frame, step.left), _operand(frame, step.right)
            frame[name] = {
                "add": np.add,
                "subtract": np.subtract,
                "multiply": np.multiply,
                "divide": np.divide,
            }[step.op](left, right)
    return apply_filter(frame, query.where)


def reproduces(
    evidence: Evidence, tables: dict[str, pd.DataFrame], rtol: float = 1e-6
) -> tuple[bool, str]:
    """Whether a compute query gives back the claimed values, with the reason when it does not."""
    if not isinstance(evidence.query, ComputeQuery):
        raise TypeError("Only compute queries are evaluated here; rule queries rerun the rule.")
    rows = evaluate(evidence.query, tables)
    if len(rows) != 1:
        return False, f"The query selects {len(rows)} rows; it must select exactly one."
    row = rows.iloc[0]
    for name, claimed in evidence.values.items():
        if name not in rows.columns:
            return False, f"The query does not compute {name!r}."
        actual = float(row[name])
        if not np.isclose(actual, claimed, rtol=rtol, atol=0.0):
            return False, f"{name} comes out as {actual:g}, not the claimed {claimed:g}."
    return True, ""
