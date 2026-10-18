from __future__ import annotations

import pandas as pd
import pytest

from src.decompose import video_cells_via_map


def test_video_cells_reject_a_judgeable_video_id_absent_from_videos() -> None:
    published = pd.DataFrame(
        {
            "video_id": ["v1", "missing"],
            "jp_realized": ["aa", "bb"],
            "dur": [0.2, 0.2],
            "jp_match": ["exact_default", "exact_default"],
            "char": ["字", "詞"],
        }
    )
    videos = pd.DataFrame(
        {
            "video_id": ["v1"],
            "period": ["pre"],
            "film_group": ["film"],
        }
    )
    with pytest.raises(
        ValueError, match=r"^judgeable syllable video_id is not in the videos frame"
    ):
        video_cells_via_map(published, videos)


def test_video_cells_keep_an_unassigned_video_that_is_in_the_frame() -> None:
    published = pd.DataFrame(
        {
            "video_id": ["v1", "v2"],
            "jp_realized": ["aa", "bb"],
            "dur": [0.2, 0.3],
            "jp_match": ["exact_default", "tone"],
            "char": ["字", "詞"],
        }
    )
    videos = pd.DataFrame(
        {
            "video_id": ["v1", "v2"],
            "period": ["pre", "unassigned_period"],
            "film_group": ["film", "other"],
        }
    )
    out = video_cells_via_map(published, videos)
    assert list(out["video_id"]) == ["v1"]
    assert int(out.loc[0, "n_judgeable"]) == 1
    assert int(out.loc[0, "n_match"]) == 1
    assert out.loc[0, "stratum"] == "film_pre"
