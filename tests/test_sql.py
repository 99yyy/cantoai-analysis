"""Every TASK-6 .sql file EXPLAINs and is named by a results.json query."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.hashing import verify_corpus_hash

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "tasks" / "TASK-6" / "sql"
RESULTS_FILE = ROOT / "tasks" / "TASK-6" / "results.json"
CORPUS_PATH = ROOT / "data" / "corpus_v2.sqlite"
README_PATH = ROOT / "README.md"


def test_explain_every_sql_file() -> None:
    verify_corpus_hash(str(CORPUS_PATH), str(README_PATH))
    conn = sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True)
    files = sorted(SQL_DIR.glob("*.sql"))
    assert files, "no sql files"
    try:
        for path in files:
            text = path.read_text(encoding="utf-8")
            conn.execute("EXPLAIN " + text)
            cur = conn.execute(text)
            rows = cur.fetchmany(2)
            assert len(rows) == 1
            assert len(rows[0]) == 1
            assert isinstance(rows[0][0], (int, float))
    finally:
        conn.close()


def test_every_sql_file_is_named_by_results() -> None:
    if not RESULTS_FILE.is_file():
        pytest.fail("tasks/TASK-6/results.json is missing")
    rows = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    named = {
        Path(r["query"]).resolve()
        for r in rows
        if isinstance(r["query"], str) and r["query"].endswith(".sql")
    }
    on_disk = {p.resolve() for p in SQL_DIR.glob("*.sql")}
    assert on_disk == named, f"sql files not named by results: {on_disk ^ named}"
