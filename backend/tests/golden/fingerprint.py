"""Compact fingerprints of tables, so golden tests can check big outputs without storing them.

A fingerprint holds the row count, the column names and, per column, summary numbers (numeric
columns) or a hash of the value counts (other columns). Two tables with the same fingerprint
agree on every column's distribution; small float noise is absorbed by the tolerance.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REFERENCE = Path(__file__).parent / "reference"


def _column(series: pd.Series) -> dict[str, Any]:
    if pd.api.types.is_bool_dtype(series):
        series = series.astype("Int64")
    if pd.api.types.is_numeric_dtype(series):
        values = pd.to_numeric(series, errors="coerce").astype(float)
        present = values.dropna()
        return {
            "kind": "number",
            "nulls": int(values.isna().sum()),
            "sum": float(present.sum()),
            "mean": float(present.mean()) if len(present) else None,
            "std": float(present.std()) if len(present) > 1 else None,
            "min": float(present.min()) if len(present) else None,
            "max": float(present.max()) if len(present) else None,
        }
    text = series.astype("string").fillna("<NA>")
    counts = text.value_counts().sort_index()
    digest = hashlib.sha256(json.dumps(list(counts.items()), default=str).encode()).hexdigest()
    return {
        "kind": "text",
        "nulls": int(series.isna().sum()),
        "distinct": len(counts),
        "hash": digest,
    }


def fingerprint(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": len(frame),
        "columns": [str(c) for c in frame.columns],
        "values": {str(c): _column(frame[c]) for c in frame.columns},
    }


def save(name: str, frame: pd.DataFrame) -> None:
    REFERENCE.mkdir(exist_ok=True)
    (REFERENCE / f"{name}.json").write_text(json.dumps(fingerprint(frame), indent=1))


def assert_matches(
    name: str, frame: pd.DataFrame, rtol: float = 1e-9, ignore: tuple[str, ...] = ()
) -> None:
    """Check `frame` against the saved fingerprint `name`, column by column."""
    expected = json.loads((REFERENCE / f"{name}.json").read_text())
    actual = fingerprint(frame)
    assert actual["rows"] == expected["rows"], (
        f"{name}: {actual['rows']} rows, expected {expected['rows']}"
    )
    want = [c for c in expected["columns"] if c not in ignore]
    got = [c for c in actual["columns"] if c not in ignore]
    assert sorted(got) == sorted(want), f"{name}: columns differ: {set(got) ^ set(want)}"
    for column in want:
        e, a = expected["values"][column], actual["values"][column]
        assert a["kind"] == e["kind"], f"{name}.{column}: {a['kind']} values, expected {e['kind']}"
        if e["kind"] == "text":
            assert a == e, f"{name}.{column}: values differ"
            continue
        assert a["nulls"] == e["nulls"], (
            f"{name}.{column}: {a['nulls']} nulls, expected {e['nulls']}"
        )
        for stat in ("sum", "mean", "std", "min", "max"):
            if e[stat] is None:
                assert a[stat] is None, f"{name}.{column}.{stat}"
            else:
                assert np.isclose(a[stat], e[stat], rtol=rtol, atol=1e-9), (
                    f"{name}.{column}.{stat}: {a[stat]} != {e[stat]}"
                )


def as_read_from_csv(frame: pd.DataFrame) -> pd.DataFrame:
    """The table as the notebooks' CSV outputs read back, so dtypes match the reference."""
    import io

    return pd.read_csv(io.StringIO(frame.to_csv(index=False)))
