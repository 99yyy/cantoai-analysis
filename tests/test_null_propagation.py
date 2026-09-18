"""Null one fixture row per enumerated column; derived measures must not stay ok."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

from src.agreement import MEASURE_COLUMNS, is_null, row_measures

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "complete_row.json"


def _schema_columns() -> set[str]:
    con = sqlite3.connect(ROOT / "fixtures" / "schema.sqlite")
    try:
        cols: set[str] = set()
        for (table,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ):
            for row in con.execute(f"PRAGMA table_info({table})"):
                cols.add(row[1])
        return cols
    finally:
        con.close()


def _sql_named_columns() -> set[str]:
    schema_cols = _schema_columns()
    found: set[str] = set()
    sql_dir = ROOT / "sql"
    for path in sql_dir.glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        for col in schema_cols:
            if col in text:
                found.add(col)
        for alias in ("t0_s", "t1_s", "window_dur", "syllable_dur"):
            if alias in text:
                found.add(alias)
    return found


def _measure_columns() -> list[str]:
    frame = yaml.safe_load((ROOT / "frame.yaml").read_text(encoding="utf-8"))
    return list(frame["measure_columns"])


def _base_row() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_complete_row_computes_from_data():
    out = row_measures(_base_row())
    assert out["n_total"] == 1
    assert out["n_total_status"] == "ok"
    assert out["agreement_status"] == "ok"


def test_null_propagation_per_column():
    columns = sorted(set(_measure_columns()) | _sql_named_columns())
    assert columns
    base = _base_row()
    for col in columns:
        row = dict(base)
        row[col] = None
        if col == "jp_match":
            try:
                row_measures(row)
            except ValueError as exc:
                assert str(exc).startswith("NULL jp_match on judgeable row")
                continue
            raise AssertionError("jp_match null on judgeable row must raise")
        out = row_measures(row)
        for measure in MEASURE_COLUMNS:
            assert is_null(out[measure]), f"{col} left {measure} populated"
            assert out[f"{measure}_status"] != "ok", f"{col} left {measure}_status ok"
