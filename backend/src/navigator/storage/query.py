"""Reading artifacts with DuckDB straight from object storage, for the API."""

from typing import Any

import duckdb
import pandas as pd

from navigator.settings import get_settings


def connect() -> duckdb.DuckDBPyConnection:
    s = get_settings()
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        """
        CREATE SECRET store (
            TYPE s3, KEY_ID ?, SECRET ?, ENDPOINT ?, USE_SSL ?, URL_STYLE 'path'
        )
        """,
        [s.s3_access_key, s.s3_secret_key, s.s3_endpoint, s.s3_secure],
    )
    return con


def read_rows(
    uri: str,
    where: str = "",
    parameters: list[Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[pd.DataFrame, int]:
    """Rows of one artifact matching an optional filter, with the total count of matches.

    `where` is a SQL condition built by the caller from whitelisted column names, with values
    passed as `parameters`.
    """
    condition = f"WHERE {where}" if where else ""
    params = parameters or []
    with connect() as con:
        source = f"read_parquet('{uri}')"
        total = con.execute(f"SELECT count(*) FROM {source} {condition}", params).fetchone()
        rows = con.execute(
            f"SELECT * FROM {source} {condition} LIMIT ? OFFSET ?", [*params, limit, offset]
        ).df()
    return rows, int(total[0]) if total else 0
