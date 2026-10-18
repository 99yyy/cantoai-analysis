from __future__ import annotations

import pandas as pd
import pytest

from src.groups import period_masks
from src.run_decomposition import year_video_counts


@pytest.mark.parametrize("bad_date", [None, "n/a"])
def test_year_video_counts_rejects_a_non_year_cell(bad_date: object) -> None:
    videos = pd.DataFrame(
        {
            "video_id": ["v1", "v2"],
            "upload_date": ["20240101", bad_date],
        }
    )
    _pre, _post, unassigned = period_masks(videos["upload_date"])
    assert list(unassigned) == [False, True]
    with pytest.raises(ValueError, match=r"^year cell is not a four-digit year"):
        year_video_counts(videos)


def test_year_video_counts_keeps_four_digit_years() -> None:
    videos = pd.DataFrame(
        {
            "video_id": ["a", "b", "c"],
            "upload_date": ["20240101", "20250102", "20240115"],
        }
    )
    assert year_video_counts(videos) == [
        {"year": "2024", "n_videos": 2},
        {"year": "2025", "n_videos": 1},
    ]
