"""Number-valued SQL lives under tasks/TASK-6/sql/."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name: str) -> str:
    if _IDENT.fullmatch(name) is None:
        raise ValueError("table name is not a simple identifier")
    return name


def load_table(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    ident = quote_ident(table)
    statement = (
        Path(__file__).resolve().with_name("tables_load.sql").read_text(encoding="utf-8")
        + ident
    )
    cursor = conn.execute(statement)
    columns = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=columns)


def open_corpus(corpus_PATH: str) -> sqlite3.Connection:
    return sqlite3.connect("file:" + corpus_PATH + "?mode=ro", uri=True)
