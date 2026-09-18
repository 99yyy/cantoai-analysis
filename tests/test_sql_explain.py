"""Smoke + falsifiable tests for the SQL EXPLAIN harness (contract §9 / §19),
plus an EXPLAIN of every sql/*.sql file against fixtures/schema.sqlite (clause 17)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.sql_explain import (
    SchemaEmptyError,
    SqlExplainError,
    UnexecutedQueryPathError,
    assert_schema_empty,
    collect_query_paths,
    explain_sql,
    prepare_working_connection,
    report_or_raise,
    run_explain_report,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "fixtures" / "schema.sqlite"


@pytest.fixture
def schema_con() -> sqlite3.Connection:
    con = prepare_working_connection(SCHEMA)
    try:
        yield con
    finally:
        con.close()


def test_explain_valid_select_against_schema(schema_con: sqlite3.Connection) -> None:
    detail = explain_sql(schema_con, "SELECT * FROM videos")
    assert detail.startswith("ok:")


def test_schema_fixture_has_zero_rows(schema_con: sqlite3.Connection) -> None:
    # Actual COUNT(*) comparison, not a file-exists check (contract §10).
    assert_schema_empty(schema_con)
    n = schema_con.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    assert n == 0


def test_explain_missing_table_is_falsifiable(schema_con: sqlite3.Connection) -> None:
    with pytest.raises(SqlExplainError):
        explain_sql(schema_con, "SELECT * FROM table_that_does_not_exist")


def test_explain_syntax_error_is_falsifiable(schema_con: sqlite3.Connection) -> None:
    with pytest.raises(SqlExplainError):
        explain_sql(schema_con, "SELEKT * FROM videos")


def test_assert_schema_empty_fails_when_rows_present() -> None:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE videos (video_id TEXT)")
    con.execute("INSERT INTO videos VALUES ('x')")
    with pytest.raises(SchemaEmptyError):
        assert_schema_empty(con)
    con.close()


def test_unresolved_execute_path_is_falsifiable() -> None:
    source = "def f(con):\n    con.execute(unknown_sql())\n"
    paths, _aux = collect_query_paths(source, relpath="anti_example.py")
    unresolved = [p for p in paths if p.sql is None and p.kind == "execute"]
    assert unresolved, "anti-example must produce an unresolved execute path"
    report = run_explain_report(ROOT, SCHEMA, paths=paths)
    with pytest.raises(UnexecutedQueryPathError):
        report_or_raise(report)


def test_repo_sql_explains_against_schema_fixture() -> None:
    report = run_explain_report(ROOT, SCHEMA)
    if report.failures or report.unresolved:
        print(report.failures)
        print(report.unresolved)
    report_or_raise(report)
    assert report.explained, "EXPLAIN harness must not be a no-op"


def test_sql_files_explain_against_schema() -> None:
    """EXPLAIN every sql/*.sql file against fixtures/schema.sqlite."""
    con = sqlite3.connect(SCHEMA)
    try:
        files = sorted((ROOT / "sql").glob("*.sql"))
        assert files
        for path in files:
            sql = path.read_text(encoding="utf-8")
            con.execute("EXPLAIN " + sql)
    finally:
        con.close()
