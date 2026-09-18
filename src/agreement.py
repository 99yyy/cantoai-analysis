"""Contract-24 agreement: n_match / n_judgeable on the judgeable set only."""

from __future__ import annotations

import pandas as pd


def judgeable_mask(df: pd.DataFrame) -> pd.Series:
    realized = df["jp_realized"].fillna("").astype(str)
    nonempty = df["jp_realized"].notna() & (realized != "")
    return nonempty & (df["dur"] > 0)


def match_mask(df: pd.DataFrame) -> pd.Series:
    return df["jp_match"].isin(("exact_default", "exact_alt"))


def assert_no_null_jp_match(df: pd.DataFrame, judgeable: pd.Series) -> None:
    if bool(df.loc[judgeable, "jp_match"].isna().any()):
        raise ValueError("judgeable syllable has NULL jp_match")


def agreement_counts(df: pd.DataFrame) -> dict[str, int]:
    empty = df["jp_realized"].isna() | (df["jp_realized"].fillna("").astype(str) == "")
    dur_le_0 = df["dur"] <= 0
    judgeable = judgeable_mask(df)
    assert_no_null_jp_match(df, judgeable)
    match = judgeable & match_mask(df)
    return {
        "n_total": int(len(df)),
        "n_match": int(match.sum()),
        "n_judgeable": int(judgeable.sum()),
        "n_empty_realized": int(empty.sum()),
        "n_dur_le_0": int(dur_le_0.sum()),
        "n_empty_and_zerodur": int((empty & dur_le_0).sum()),
    }
