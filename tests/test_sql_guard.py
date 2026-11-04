"""The SELECT-only guard and the DuckDB sandbox behind query_lakehouse."""

from __future__ import annotations

import pytest

from mle_starter.lakehouse import SqlGuardError, guard_sql, run_query

ALLOWED = [
    "SELECT count(*) FROM features",
    "select * from raw limit 5;",
    "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
    "FROM features SELECT split, count(*) GROUP BY 1",
    "DESCRIBE features",
    "SELECT 'drop table x' AS harmless_string",
    "-- a comment\nSELECT 1",
]

REJECTED = [
    ("DROP TABLE features", "DROP"),
    ("INSERT INTO features VALUES (1)", "INSERT"),
    ("COPY (SELECT * FROM features) TO 'out.csv'", "COPY"),
    ("ATTACH 'other.duckdb' AS o", "ATTACH"),
    ("SELECT 1; DROP TABLE features", "DROP"),
    ("SELECT 1; SELECT 2", "exactly one statement"),
    ("CREATE TABLE t AS SELECT 1", "CREATE"),
    ("UPDATE features SET age = 1", "UPDATE"),
    ("DELETE FROM features", "DELETE"),
    ("PRAGMA version", "PRAGMA"),
    ("SET enable_external_access = true", "SET"),
    ("INSTALL httpfs", "INSTALL"),
    ("LOAD httpfs", "LOAD"),
    ("/* sneaky */ DROP TABLE features", "DROP"),
    ("WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x", "INSERT"),
    ("", "empty"),
    ("-- only a comment", "only comments"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_read_only_queries_pass_the_guard(sql):
    assert guard_sql(sql)


@pytest.mark.parametrize("sql,reason", REJECTED)
def test_write_and_side_effect_queries_are_rejected(sql, reason):
    with pytest.raises(SqlGuardError, match=reason):
        guard_sql(sql)


def test_query_runs_and_reports_shape(lakehouse_dir):
    res = run_query(lakehouse_dir, "SELECT split, count(*) AS n FROM features GROUP BY 1 ORDER BY 1", 50, 500)
    assert res["columns"] == ["split", "n"]
    assert dict(res["rows"]) == {"test": res["rows"][0][1], "train": res["rows"][1][1]}
    assert sum(r[1] for r in res["rows"]) == 50_000
    assert res["truncated"] is False


def test_row_cap_truncates(lakehouse_dir):
    res = run_query(lakehouse_dir, "SELECT applicant_id FROM raw", 10_000, 25)
    assert res["row_count"] == 25 and res["truncated"] is True and res["row_cap"] == 25


def test_sandbox_blocks_files_outside_the_lakehouse(lakehouse_dir):
    with pytest.raises(SqlGuardError, match="query failed"):
        run_query(lakehouse_dir, "SELECT * FROM read_csv('/etc/hosts')", 5, 500)


def test_sandbox_config_is_locked(lakehouse_dir):
    from mle_starter.lakehouse import connect_readonly

    con = connect_readonly(lakehouse_dir)
    with pytest.raises(Exception, match="(?i)configuration"):
        con.execute("SET enable_external_access = true")
