"""Every DataFrame join goes through checked_merge."""

from __future__ import annotations

import pandas as pd

from src.pins import FrameCounts

JOIN_SPEC = {
    "syllables_windows": {
        "on": ["uid"],
        "expected_field": "syllables_expected",
    },
    "published_syllables_videos": {
        "on": ["video_id"],
        "expected_field": "published_expected",
    },
}

_BOUND: FrameCounts | None = None


def bind_frame_counts(counts: FrameCounts) -> None:
    global _BOUND
    _BOUND = counts


def unbind_frame_counts() -> None:
    global _BOUND
    _BOUND = None


def _expected_count(spec: dict, expected_rows: int | None) -> int:
    if expected_rows is None:
        if _BOUND is None:
            raise ValueError("checked_merge expected count is not bound from the frame")
        return int(getattr(_BOUND, spec["expected_field"]))
    if type(expected_rows) is not int:
        raise ValueError("checked_merge expected count is not an int")
    return expected_rows


def checked_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    join_name: str,
    expected_rows: int | None = None,
) -> pd.DataFrame:
    if join_name not in JOIN_SPEC:
        raise ValueError("checked_merge join_name is not a declared join")
    spec = JOIN_SPEC[join_name]
    expected = _expected_count(spec, expected_rows)
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
    if len(both) != expected:
        print(len(both), expected)
        if join_name == "syllables_windows":
            raise ValueError(
                "checked_merge syllables_windows: row count is not the declared expected count"
            )
        if join_name == "published_syllables_videos":
            raise ValueError(
                "checked_merge published_syllables_videos: row count is not the declared expected count"
            )
        raise ValueError("checked_merge join_name is not a declared join")
    both.attrs["unmatched_left"] = unmatched_left
    both.attrs["join_name"] = join_name
    return both.reset_index(drop=True)
