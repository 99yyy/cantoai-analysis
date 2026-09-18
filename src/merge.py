"""Single DataFrame join helper. pd.merge lives only in this module."""

from __future__ import annotations

from typing import Any

import pandas as pd

JOIN_KEYS_MISMATCH = "checked_merge join keys do not match frame.yaml joins"
JOIN_NAME_MISSING = "join_name missing from frame.yaml joins"
DUPLICATE_OUTPUT = "duplicate output column or key"


def assert_unique_columns(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise ValueError(DUPLICATE_OUTPUT)


def checked_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    join_name: str,
    frame: dict[str, Any],
) -> pd.DataFrame:
    joins = frame.get("joins") or {}
    if join_name not in joins:
        raise ValueError(JOIN_NAME_MISSING)
    spec = joins[join_name]
    keys = list(spec["keys"])
    merge_keys = keys
    if merge_keys != list(spec["keys"]):
        raise ValueError(JOIN_KEYS_MISMATCH)
    overlap = (set(left.columns) & set(right.columns)) - set(merge_keys)
    if overlap:
        raise ValueError(DUPLICATE_OUTPUT)
    assert_unique_columns(list(left.columns))
    assert_unique_columns(list(right.columns))
    merged = pd.merge(left, right, on=merge_keys, how="left", indicator=True)
    assert_unique_columns([c for c in merged.columns if c != "_merge"])
    expected_rows = spec["expected_rows"]
    matched = int((merged["_merge"] == "both").sum())
    if matched != expected_rows:
        raise ValueError(JOIN_KEYS_MISMATCH)
    return merged.drop(columns=["_merge"])
