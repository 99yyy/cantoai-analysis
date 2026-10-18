from __future__ import annotations

import pandas as pd
import pytest

from src.decompose import video_cells_via_map


def _published() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "video_id": ["v1"],
            "jp_realized": ["aa"],
            "dur": [0.2],
            "jp_match": ["exact_default"],
            "char": ["字"],
        }
    )


def test_video_cells_reject_a_repeated_video_id() -> None:
    videos = pd.DataFrame(
        {
            "video_id": ["v1", "v1"],
            "period": ["pre", "pre"],
            "film_group": ["film", "film"],
        }
    )
    with pytest.raises(ValueError, match=r"^video cells repeat a video_id"):
        video_cells_via_map(_published(), videos)


def test_video_cells_keep_one_count_per_video_id() -> None:
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
            "video_id": ["v2", "v1"],
            "period": ["post", "pre"],
            "film_group": ["other", "film"],
        }
    )
    out = video_cells_via_map(published, videos)
    got = list(zip(out["video_id"], out["stratum"], out["n_judgeable"], out["n_match"]))
    assert got == [
        ("v2", "other_post", 1, 0),
        ("v1", "film_pre", 1, 1),
    ]
