"""Every DataFrame join goes through checked_merge with a literal row count."""

from __future__ import annotations

import pandas as pd

JOIN_SPEC = {
    "syllables_windows": {
        "on": ["uid"],
        "expected": 171867,
    },
    "published_syllables_videos": {
        "on": ["video_id"],
        "expected": 164693,
    },
}


def checked_merge(left: pd.DataFrame, right: pd.DataFrame, join_name: str) -> pd.DataFrame:
    if join_name not in JOIN_SPEC:
        raise ValueError("checked_merge join_name is not a declared join")
    spec = JOIN_SPEC[join_name]
    merged = pd.merge(
        left,
        right,
        on=list(spec["on"]),
        how="left",
        indicator=True,
        suffixes=("", "_right"),
    )
    unmatched_left = int((merged["_merge"] == "left_only").sum())
    both = merged.loc[merged["_merge"] == "both"].drop(columns=["_merge"])
    if len(both) != spec["expected"]:
        print(len(both), spec["expected"])
        if join_name == "syllables_windows":
            raise ValueError("checked_merge syllables_windows: row count is not 171867")
        if join_name == "published_syllables_videos":
            raise ValueError("checked_merge published_syllables_videos: row count is not 164693")
        raise ValueError("checked_merge join_name is not a declared join")
    both.attrs["unmatched_left"] = unmatched_left
    both.attrs["join_name"] = join_name
    return both.reset_index(drop=True)
