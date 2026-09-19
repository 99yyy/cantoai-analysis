"""Declared sampling-frame counts: task ```frame``` fence, README table sizes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FRAME_FENCE = re.compile(r"^```frame\s*$(.*?)^```\s*$", re.M | re.S)
README_TABLE = re.compile(r"`(videos|windows|syllables)`\s*\((\d+)\)")

REQUIRED_EXPECTED = (
    "videos_expected",
    "windows_expected",
    "syllables_expected",
    "published_expected",
)
README_TO_FRAME = (
    ("videos", "videos_expected"),
    ("windows", "windows_expected"),
    ("syllables", "syllables_expected"),
)


@dataclass(frozen=True)
class FrameCounts:
    videos_expected: int
    windows_expected: int
    syllables_expected: int
    published_expected: int
    videos_expected_tol: int
    windows_expected_tol: int
    syllables_expected_tol: int
    published_expected_tol: int


def parse_frame_entries(text: str) -> dict[str, float]:
    match = FRAME_FENCE.search(text)
    if match is None:
        raise ValueError("task brief has no frame fence")
    out: dict[str, float] = {}
    for raw in match.group(1).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        nums: list[float] = []
        ok = True
        for piece in parts[1:]:
            try:
                nums.append(float(piece))
            except ValueError:
                ok = False
                break
        if not ok or len(nums) != 1:
            continue
        name = parts[0]
        if name in out:
            raise ValueError("frame declares a name twice")
        out[name] = nums[0]
    return out


def parse_readme_table_sizes(readme_PATH: str) -> dict[str, int]:
    text = Path(readme_PATH).read_text(encoding="utf-8")
    found = {name: int(n) for name, n in README_TABLE.findall(text)}
    if any(name not in found for name in ("videos", "windows", "syllables")):
        raise ValueError("README.md records no table sizes")
    return found


def _whole_count(value: float) -> int:
    n = int(value)
    if float(n) != value:
        raise ValueError("frame expected count is not a whole number")
    return n


def load_frame_counts(brief_PATH: str, readme_PATH: str) -> FrameCounts:
    entries = parse_frame_entries(Path(brief_PATH).read_text(encoding="utf-8"))
    for name in REQUIRED_EXPECTED:
        if name not in entries:
            print(name)
            raise ValueError("frame is missing a required expected count")
    readme = parse_readme_table_sizes(readme_PATH)
    for table, field in README_TO_FRAME:
        frame_n = _whole_count(entries[field])
        readme_n = readme[table]
        if frame_n != readme_n:
            print(table, frame_n, readme_n)
            raise ValueError("frame count does not match README table size")
    return FrameCounts(
        videos_expected=_whole_count(entries["videos_expected"]),
        windows_expected=_whole_count(entries["windows_expected"]),
        syllables_expected=_whole_count(entries["syllables_expected"]),
        published_expected=_whole_count(entries["published_expected"]),
        videos_expected_tol=_tol(entries, "videos_expected_tol"),
        windows_expected_tol=_tol(entries, "windows_expected_tol"),
        syllables_expected_tol=_tol(entries, "syllables_expected_tol"),
        published_expected_tol=_tol(entries, "published_expected_tol"),
    )


def _tol(entries: dict[str, float], name: str) -> int:
    if name not in entries:
        return 0
    return _whole_count(entries[name])
