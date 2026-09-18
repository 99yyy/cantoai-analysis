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
    *,
    enforce_expected: bool = True,
    row_accounting: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    joins = frame.get("joins") or {}
    if join_name not in joins:
        raise ValueError(JOIN_NAME_MISSING)
    spec = joins[join_name]
    keys = list(spec["keys"])
    right_work = right.copy()
    right_key = spec.get("right_key")
    if right_key is not None and right_key not in keys:
        if len(keys) != 1:
            raise ValueError(JOIN_KEYS_MISMATCH)
        if right_key not in right_work.columns:
            raise ValueError(JOIN_KEYS_MISMATCH)
        right_work = right_work.rename(columns={right_key: keys[0]})
    merge_keys = keys
    if merge_keys != list(spec["keys"]):
        raise ValueError(JOIN_KEYS_MISMATCH)
    overlap = (set(left.columns) & set(right_work.columns)) - set(merge_keys)
    if overlap:
        raise ValueError(DUPLICATE_OUTPUT)
    assert_unique_columns(list(left.columns))
    assert_unique_columns(list(right_work.columns))
    before = len(left)
    merged = pd.merge(left, right_work, on=merge_keys, how="left", indicator=True)
    assert_unique_columns([c for c in merged.columns if c != "_merge"])
    expected_rows = spec["expected_rows"]
    matched = int((merged["_merge"] == "both").sum())
    if enforce_expected and matched != expected_rows:
        raise ValueError(JOIN_KEYS_MISMATCH)
    if row_accounting is not None:
        row_accounting.append(
            {
                "step": f"join_{join_name}",
                "rule": f"checked_merge:{join_name}",
                "group": "all",
                "rows_before": before,
                "rows_after": len(merged),
            }
        )
    return merged.drop(columns=["_merge"])


def left_attach(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: list[str],
    *,
    step: str,
    row_accounting: list[dict[str, Any]],
) -> pd.DataFrame:
    """Left-attach columns via merge; records row_accounting. No expected_rows gate."""
    overlap = (set(left.columns) & set(right.columns)) - set(on)
    if overlap:
        raise ValueError(DUPLICATE_OUTPUT)
    assert_unique_columns(list(left.columns))
    assert_unique_columns(list(right.columns))
    before = len(left)
    merged = pd.merge(left, right, on=on, how="left", indicator=True)
    assert_unique_columns([c for c in merged.columns if c != "_merge"])
    row_accounting.append(
        {
            "step": step,
            "rule": f"left_attach on {','.join(on)}",
            "group": "all",
            "rows_before": before,
            "rows_after": int((merged["_merge"] == "both").sum()),
        }
    )
    return merged.drop(columns=["_merge"])
