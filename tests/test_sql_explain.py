"""EXPLAIN every sql/*.sql file against fixtures/schema.sqlite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sql_explain_against_schema():
    schema = ROOT / "fixtures" / "schema.sqlite"
    con = sqlite3.connect(schema)
    try:
        files = sorted((ROOT / "sql").glob("*.sql"))
        assert files
        for path in files:
            sql = path.read_text(encoding="utf-8")
            con.execute("EXPLAIN " + sql)
    finally:
        con.close()
