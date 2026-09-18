"""Load sqlite tables. Number-valued SQL lives under tasks/TASK-6/sql/."""

from __future__ import annotations

import re
import sqlite3

import pandas as pd

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name: str) -> str:
    if _IDENT.fullmatch(name) is None:
        raise ValueError("table name is not a simple identifier")
    return name


def load_table(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    ident = quote_ident(table)
    cursor = conn.execute("select * from " + ident)
    columns = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=columns)


def open_corpus(corpus_PATH: str) -> sqlite3.Connection:
    return sqlite3.connect("file:" + corpus_PATH + "?mode=ro", uri=True)
