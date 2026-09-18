"""Measure columns carry a companion status; sentinels are not ok values."""

from __future__ import annotations

import pandas as pd

FORBIDDEN_STATUS = ("unknown", "other")


def flatten_key(parts: list[str], sep: str = "\x1f") -> str:
    for part in parts:
        if sep in part:
            raise ValueError("flattened key separator occurs inside a key segment")
    return sep.join(parts)


def ensure_unique_columns(df: pd.DataFrame, new_name: str) -> None:
    if new_name in df.columns:
        raise ValueError("duplicate column in output frame")


def assert_status_matches_values(values: pd.Series, status: pd.Series) -> None:
    if bool(status.isin(FORBIDDEN_STATUS).any()):
        raise ValueError("unknown and other are not allowed measure status values")
    ok = status == "ok"
    present = values.notna()
    if bool((ok != present).any()):
        raise ValueError("measure status ok is not exactly the non-NULL value set")


def assert_no_measure_sentinel(
    values: pd.Series, status: pd.Series, n_judgeable: pd.Series
) -> None:
    missing = (n_judgeable == 0) | n_judgeable.isna()
    bad = missing & (status == "ok")
    if bool(bad.any()):
        raise ValueError("measure sentinel written with status ok")


def attach_agreement(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ensure_unique_columns(out, "agreement")
    ensure_unique_columns(out, "agreement_status")
    n_j = out["n_judgeable"]
    n_m = out["n_match"]
    values = pd.Series(pd.NA, index=out.index, dtype="Float64")
    ok_rows = n_j > 0
    values.loc[ok_rows] = (n_m.loc[ok_rows] / n_j.loc[ok_rows]).astype(float)
    status = pd.Series("missing", index=out.index)
    status.loc[ok_rows] = "ok"
    assert_status_matches_values(values, status)
    assert_no_measure_sentinel(values, status, n_j)
    out["agreement"] = values
    out["agreement_status"] = status
    return out
