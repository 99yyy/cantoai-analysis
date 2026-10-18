from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from src.frame import load_published_frame
from src.joins import bind_frame_counts, checked_merge, unbind_frame_counts
from src.pins import FrameCounts
from src.tables import open_corpus

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "data" / "corpus_v2.sqlite"
README_PATH = ROOT / "README.md"
BRIEF_PATH = ROOT / "tasks" / "TASK-6.md"


def _counts(syllables_expected: int) -> FrameCounts:
    return FrameCounts(
        videos_expected=4,
        windows_expected=4,
        syllables_expected=syllables_expected,
        published_expected=4,
        videos_expected_tol=0,
        windows_expected_tol=0,
        syllables_expected_tol=0,
        published_expected_tol=0,
    )


def _pair(n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    uid = list(range(n))
    left = pd.DataFrame({"uid": uid, "tier": ["C"] * n, "video_id": ["not-a-channel-video"] * n})
    right = pd.DataFrame(
        {"uid": uid, "window_tier": ["C"] * n, "video_id": ["not-a-channel-video"] * n}
    )
    return left, right


def test_explicit_count_wins_over_stale_bind() -> None:
    bind_frame_counts(_counts(99))
    left, right = _pair(2)
    try:
        merged = checked_merge(left, right, "syllables_windows", 2)
    finally:
        unbind_frame_counts()
    assert merged["tier"].tolist() == ["C", "C"]
    assert merged["video_id"].tolist() == ["not-a-channel-video", "not-a-channel-video"]
    assert int(merged.attrs["unmatched_left"]) == 0


def test_explicit_count_rejects_rows_that_match_the_stale_bind() -> None:
    bind_frame_counts(_counts(2))
    left, right = _pair(2)
    try:
        with pytest.raises(
            ValueError,
            match=r"^checked_merge syllables_windows: row count is not the declared expected count",
        ):
            checked_merge(left, right, "syllables_windows", 4)
    finally:
        unbind_frame_counts()


def test_expected_count_rejects_bool() -> None:
    left, right = _pair(1)
    with pytest.raises(ValueError, match=r"^checked_merge expected count is not an int"):
        checked_merge(left, right, "syllables_windows", True)


def test_load_published_frame_does_not_publish_its_count() -> None:
    bind_frame_counts(_counts(4))
    try:
        conn = open_corpus(str(CORPUS_PATH))
        try:
            loaded = load_published_frame(conn, str(BRIEF_PATH), str(README_PATH))
        finally:
            conn.close()
        assert len(loaded["published"]) == 164693
        left, right = _pair(4)
        merged = checked_merge(left, right, "syllables_windows")
        assert merged["video_id"].tolist() == ["not-a-channel-video"] * 4
    finally:
        unbind_frame_counts()
    left, right = _pair(171867)
    with pytest.raises(
        ValueError, match=r"^checked_merge expected count is not bound from the frame"
    ):
        checked_merge(left, right, "syllables_windows")


def test_src_checked_merge_calls_pass_an_expected_count() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            else:
                continue
            if name != "checked_merge":
                continue
            starred = any(isinstance(arg, ast.Starred) for arg in node.args) or any(
                kw.arg is None for kw in node.keywords
            )
            if starred:
                offenders.append(f"{path.name}:{node.lineno} starred")
                continue
            expected = node.args[3] if len(node.args) >= 4 else None
            for kw in node.keywords:
                if kw.arg == "expected_rows":
                    expected = kw.value
            if expected is None or isinstance(expected, ast.Call):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
