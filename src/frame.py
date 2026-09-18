"""Published-set sampling frame: windows.tier IN ('A','B') on the pinned corpus."""

from __future__ import annotations

import sqlite3

import pandas as pd

from src.joins import checked_merge
from src.tables import load_table

VIDEOS_N = 567
WINDOWS_N = 4911
SYLLABLES_N = 171867
PUBLISHED_N = 164693


def assert_videos_count(n: int) -> None:
    if n != VIDEOS_N:
        print(n, VIDEOS_N)
        raise ValueError("videos row count is outside the declared interval")


def assert_windows_count(n: int) -> None:
    if n != WINDOWS_N:
        print(n, WINDOWS_N)
        raise ValueError("windows row count is outside the declared interval")


def assert_syllables_count(n: int) -> None:
    if n != SYLLABLES_N:
        print(n, SYLLABLES_N)
        raise ValueError("syllables row count is outside the declared interval")


def assert_published_count(n: int) -> None:
    if n != PUBLISHED_N:
        print(n, PUBLISHED_N)
        raise ValueError("published A+B syllable count is outside the declared interval")


def apply_tier_whitelist(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[df["window_tier"].isin(("A", "B"))].copy()


def assert_tier_matches_window(df: pd.DataFrame) -> None:
    if bool((df["tier"] != df["window_tier"]).any()):
        raise ValueError("syllable tier does not match window tier")


def load_published_frame(conn: sqlite3.Connection) -> dict:
    videos = load_table(conn, "videos")
    assert_videos_count(len(videos))
    windows = load_table(conn, "windows")
    assert_windows_count(len(windows))
    syllables = load_table(conn, "syllables")
    assert_syllables_count(len(syllables))

    steps = [
        {
            "step": "load_videos",
            "rule": "videos full table",
            "group": "all",
            "rows_before": len(videos),
            "rows_after": len(videos),
        },
        {
            "step": "load_windows",
            "rule": "windows full table",
            "group": "all",
            "rows_before": len(windows),
            "rows_after": len(windows),
        },
        {
            "step": "load_syllables",
            "rule": "syllables full table",
            "group": "all",
            "rows_before": len(syllables),
            "rows_after": len(syllables),
        },
    ]

    win_cols = windows[["uid", "video_id", "tier"]].rename(columns={"tier": "window_tier"})
    merged = checked_merge(syllables, win_cols, "syllables_windows")
    if "video_id_right" in merged.columns:
        merged = merged.drop(columns=["video_id_right"])
    steps.append(
        {
            "step": "join_syllables_windows",
            "rule": "inner uid",
            "group": "all",
            "rows_before": len(syllables),
            "rows_after": len(merged),
            "unmatched_left": int(merged.attrs.get("unmatched_left", 0)),
        }
    )
    assert_tier_matches_window(merged)

    before_tier = len(merged)
    published = apply_tier_whitelist(merged)
    assert_published_count(len(published))
    steps.append(
        {
            "step": "tier_whitelist",
            "rule": "windows.tier IN ('A','B')",
            "group": "all",
            "rows_before": before_tier,
            "rows_after": len(published),
        }
    )

    vid_cols = videos[["video_id", "title", "upload_date"]]
    published = checked_merge(published, vid_cols, "published_syllables_videos")
    steps.append(
        {
            "step": "join_published_videos",
            "rule": "inner video_id",
            "group": "all",
            "rows_before": PUBLISHED_N,
            "rows_after": len(published),
            "unmatched_left": int(published.attrs.get("unmatched_left", 0)),
        }
    )
    return {
        "videos": videos,
        "windows": windows,
        "syllables": syllables,
        "published": published,
        "steps": steps,
    }
