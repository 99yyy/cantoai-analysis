"""Clause 11: only src/tables.py may hold SELECT/FROM load SQL."""

from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path

from src.tables import load_table

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
LOADER_FILE = SRC_ROOT / "tables.py"
WORD_SELECT = re.compile(r"(?i)\bSELECT\b")
WORD_FROM = re.compile(r"(?i)\bFROM\b")
HONEST_LOAD = re.compile(r"\bSELECT\b.+\bFROM\b")


def _literal_strings(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((int(getattr(node, "lineno", 0)), node.value))
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    parts.append(" ")
            found.append((int(getattr(node, "lineno", 0)), "".join(parts)))
    return found


def select_from_hits(src_DIR: Path) -> list[str]:
    """Return path:line hits for string literals with both SELECT and FROM."""
    hits: list[str] = []
    for path in sorted(src_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.resolve().as_posix()
        for lineno, text in _literal_strings(tree):
            if WORD_SELECT.search(text) and WORD_FROM.search(text):
                hits.append(f"{rel}:{lineno}")
    return hits


def test_only_tables_py_may_hold_select_from_sql() -> None:
    hits = select_from_hits(SRC_ROOT)
    allowed_prefix = LOADER_FILE.resolve().as_posix() + ":"
    foreign = [h for h in hits if not h.startswith(allowed_prefix)]
    assert foreign == [], foreign


def test_tables_py_load_sql_is_honest_uppercase_select_from() -> None:
    tree = ast.parse(LOADER_FILE.read_text(encoding="utf-8"))
    honest = [
        text
        for _, text in _literal_strings(tree)
        if HONEST_LOAD.search(text)
    ]
    assert honest, "src/tables.py has no honest uppercase SELECT/FROM load SQL"
    assert any("SELECT * FROM" in text for text in honest)


def test_select_from_scan_goes_red_on_injected_non_loader_sql(tmp_path: Path) -> None:
    src_DIR = tmp_path / "src"
    src_DIR.mkdir()
    (src_DIR / "other.py").write_text(
        'Q = "select * from videos"\n',
        encoding="utf-8",
    )
    hits = select_from_hits(src_DIR)
    assert hits, "scan stayed green on lowercase SELECT/FROM outside the loader"


def test_load_table_runs_honest_select(tmp_path: Path) -> None:
    db_FILE = tmp_path / "t.sqlite"
    conn = sqlite3.connect(str(db_FILE))
    conn.execute("CREATE TABLE videos (id INTEGER)")
    conn.execute("INSERT INTO videos VALUES (7)")
    conn.commit()
    try:
        frame = load_table(conn, "videos")
    finally:
        conn.close()
    assert list(frame.columns) == ["id"]
    assert frame["id"].tolist() == [7]
