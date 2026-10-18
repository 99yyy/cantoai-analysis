from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from src.tables import load_table, quote_ident

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SELECT_WORD = re.compile(r"(?i)\bselect\b")
LOADER = "src/tables_load.sql"
LOADER_TEXT = "select * from \n"


def test_src_python_files_have_no_select() -> None:
    bad: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if SELECT_WORD.search(path.read_text(encoding="utf-8")):
            bad.append(path.relative_to(ROOT).as_posix())
    assert bad == []


def test_loader_statement_file_is_only_the_star_prefix() -> None:
    sql_files = sorted(path.relative_to(ROOT).as_posix() for path in SRC.rglob("*.sql"))
    assert sql_files == [LOADER]
    assert (ROOT / LOADER).read_text(encoding="utf-8") == LOADER_TEXT


def test_load_table_returns_every_inserted_row() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("create table videos (video_id text, title text)")
    conn.execute("insert into videos (video_id, title) values ('v1', '片'), ('v2', '歌')")
    try:
        loaded = load_table(conn, "videos")
    finally:
        conn.close()
    assert list(loaded.columns) == ["video_id", "title"]
    assert loaded["video_id"].tolist() == ["v1", "v2"]
    assert loaded["title"].tolist() == ["片", "歌"]


def test_load_table_rejects_a_statement_break() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("create table videos (video_id text)")
    conn.execute("insert into videos (video_id) values ('v1')")
    try:
        with pytest.raises(ValueError, match=r"^table name is not a simple identifier"):
            load_table(conn, "videos; drop table videos")
        remaining = conn.execute("select count(*) from videos").fetchone()
        assert remaining == (1,)
    finally:
        conn.close()


def test_quote_ident_accepts_a_plain_name() -> None:
    assert quote_ident("syllables") == "syllables"
