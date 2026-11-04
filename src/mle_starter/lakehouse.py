"""Read-only SQL over the parquet "lakehouse" with DuckDB.

Three independent guards, so one bug does not open a write path:
  1. Parse: DuckDB's own parser must see exactly one statement, of type SELECT,
     and the text must start with SELECT / WITH / FROM / DESCRIBE / SUMMARIZE.
  2. Deny-list: statements that mention write or side-effect keywords are refused
     even if the parser would call them a SELECT (e.g. PRAGMA).
  3. Sandbox: the DuckDB connection is in-memory, external access is limited to
     the lakehouse directory, and the configuration is locked.
On top of that, the MCP container mounts lakehouse/ read-only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import duckdb

ALLOWED_LEADING = ("select", "with", "from", "describe", "summarize")
FORBIDDEN = (
    "insert", "update", "delete", "merge", "drop", "create", "alter", "truncate",
    "copy", "attach", "detach", "install", "load", "pragma", "set", "reset",
    "export", "import", "call", "checkpoint", "vacuum", "grant", "revoke", "use",
)  # fmt: skip
_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN) + r")\b", re.IGNORECASE)
_COMMENTS_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_STRINGS_RE = re.compile(r"'(?:[^']|'')*'")


class SqlGuardError(ValueError):
    pass


def guard_sql(sql: str) -> str:
    """Return the cleaned statement or raise SqlGuardError with a clear reason."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlGuardError("empty query")
    cleaned = _COMMENTS_RE.sub(" ", sql).strip().rstrip(";").strip()
    if not cleaned:
        raise SqlGuardError("query contains only comments")
    first = cleaned.split(None, 1)[0].lower()
    if first not in ALLOWED_LEADING:
        raise SqlGuardError(
            f"only read-only queries are allowed (SELECT/WITH/FROM/DESCRIBE/SUMMARIZE); got {first.upper()}"
        )
    hit = _FORBIDDEN_RE.search(_STRINGS_RE.sub("''", cleaned))
    if hit:
        raise SqlGuardError(f"keyword {hit.group(1).upper()} is not allowed in read-only queries")
    try:
        statements = duckdb.connect().extract_statements(cleaned)
    except duckdb.Error as err:
        raise SqlGuardError(f"SQL does not parse: {err}") from None
    if len(statements) != 1:
        raise SqlGuardError(f"exactly one statement is allowed; got {len(statements)}")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise SqlGuardError(f"only SELECT statements are allowed; got {statements[0].type.name}")
    return cleaned


def connect_readonly(lakehouse_dir: Path) -> duckdb.DuckDBPyConnection:
    root = Path(lakehouse_dir).resolve()
    if not (root / "_manifest.json").is_file():
        raise FileNotFoundError(f"no lakehouse at {root}; run `make seed` first")
    con = duckdb.connect(":memory:")
    for name, pattern in {
        "raw": "raw/application_month=*/part-*.parquet",
        "features": "features/split=*/part-*.parquet",
    }.items():
        glob = (root / pattern).as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{glob}', hive_partitioning = true)")
    root_sql = root.as_posix().replace("'", "''")
    con.execute(f"SET allowed_directories = ['{root_sql}']")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if v == v else None  # NaN -> null
    try:
        json.dumps(v)
        return v
    except TypeError:
        return str(v)


def run_query(lakehouse_dir: Path, sql: str, max_rows: int, hard_cap: int) -> dict[str, Any]:
    cleaned = guard_sql(sql)
    limit = max(1, min(int(max_rows), int(hard_cap)))
    con = connect_readonly(lakehouse_dir)
    try:
        cur = con.execute(f"SELECT * FROM ({cleaned}) AS q LIMIT {limit + 1}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    except duckdb.Error as err:
        raise SqlGuardError(f"query failed: {err}") from None
    finally:
        con.close()
    truncated = len(rows) > limit
    rows = rows[:limit]
    return {
        "columns": cols,
        "rows": [[_jsonable(v) for v in r] for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "row_cap": limit,
    }


def describe_tables(lakehouse_dir: Path) -> dict[str, list[dict[str, str]]]:
    con = connect_readonly(lakehouse_dir)
    try:
        return {
            t: [{"column": r[0], "type": r[1]} for r in con.execute(f"DESCRIBE {t}").fetchall()]
            for t in ("raw", "features")
        }
    finally:
        con.close()
