"""Load SQL files by name. The only src module allowed to contain SELECT/FROM literals."""

from __future__ import annotations

from pathlib import Path

LOAD_SQL_CANNOT_LOCATE = "load_sql cannot locate SQL file"


def load_sql(name: str, sql_dir_PATH: str) -> str:
    if not sql_dir_PATH:
        raise FileNotFoundError(LOAD_SQL_CANNOT_LOCATE)
    filename = name if name.endswith(".sql") else f"{name}.sql"
    path = Path(sql_dir_PATH) / filename
    if not path.is_file():
        raise FileNotFoundError(LOAD_SQL_CANNOT_LOCATE)
    text = path.read_text(encoding="utf-8")
    if "SELECT" not in text or "FROM" not in text:
        raise FileNotFoundError(LOAD_SQL_CANNOT_LOCATE)
    return text
