"""Published-set sampling frame: windows.tier IN ('A','B') on the pinned corpus."""

from __future__ import annotations

import sqlite3

import pandas as pd

from src.joins import bind_frame_counts, checked_merge
from src.pins import FrameCounts, load_frame_counts
from src.tables import load_table


def _outside_interval(n: int, expected: int, tol: int) -> bool:
    return abs(n - expected) > tol


def assert_videos_count(n: int, expected: int, tol: int) -> None:
    if _outside_interval(n, expected, tol):
        print(n, expected, tol)
        raise ValueError("videos row count is outside the declared interval")


def assert_windows_count(n: int, expected: int, tol: int) -> None:
    if _outside_interval(n, expected, tol):
        print(n, expected, tol)
        raise ValueError("windows row count is outside the declared interval")


def assert_syllables_count(n: int, expected: int, tol: int) -> None:
    if _outside_interval(n, expected, tol):
        print(n, expected, tol)
        raise ValueError("syllables row count is outside the declared interval")


def assert_published_count(n: int, expected: int, tol: int) -> None:
    if _outside_interval(n, expected, tol):
        print(n, expected, tol)
        raise ValueError("published A+B syllable count is outside the declared interval")


def apply_tier_whitelist(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[df["window_tier"].isin(("A", "B"))].copy()


def assert_tier_matches_window(df: pd.DataFrame) -> None:
    if bool((df["tier"] != df["window_tier"]).any()):
        raise ValueError("syllable tier does not match window tier")


def load_published_frame(
    conn: sqlite3.Connection, brief_PATH: str, readme_PATH: str
) -> dict:
    counts = load_frame_counts(brief_PATH, readme_PATH)
    bind_frame_counts(counts)
    return _assemble_published_frame(conn, counts)


def _assemble_published_frame(conn: sqlite3.Connection, counts: FrameCounts) -> dict:
    videos = load_table(conn, "videos")
    assert_videos_count(len(videos), counts.videos_expected, counts.videos_expected_tol)
    windows = load_table(conn, "windows")
    assert_windows_count(len(windows), counts.windows_expected, counts.windows_expected_tol)
    syllables = load_table(conn, "syllables")
    assert_syllables_count(
        len(syllables), counts.syllables_expected, counts.syllables_expected_tol
    )

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
    assert_published_count(
        len(published), counts.published_expected, counts.published_expected_tol
    )
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
            "rows_before": counts.published_expected,
            "rows_after": len(published),
            "unmatched_left": int(published.attrs.get("unmatched_left", 0)),
        }
    )
    return {
        "videos": videos,
        "windows": windows,
        "syllables": syllables,
        "published": published,
        "counts": counts,
        "steps": steps,
    }
