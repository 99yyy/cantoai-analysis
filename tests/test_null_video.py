from __future__ import annotations

import pandas as pd
import pytest

from src.decompose import video_cells_via_map


def _videos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "video_id": ["v1"],
            "period": ["pre"],
            "film_group": ["film"],
        }
    )


def test_video_cells_reject_a_null_video_id_on_a_judgeable_syllable() -> None:
    published = pd.DataFrame(
        {
            "video_id": ["v1", None],
            "jp_realized": ["aa", "bb"],
            "dur": [0.2, 0.2],
            "jp_match": ["exact_default", "exact_default"],
            "char": ["字", "詞"],
        }
    )
    with pytest.raises(ValueError, match=r"^judgeable syllable has NULL video_id"):
        video_cells_via_map(published, _videos())


def test_video_cells_keep_a_non_judgeable_null_video_id() -> None:
    published = pd.DataFrame(
        {
            "video_id": ["v1", None],
            "jp_realized": ["aa", "bb"],
            "dur": [0.2, 0.0],
            "jp_match": ["exact_default", "exact_default"],
            "char": ["字", "詞"],
        }
    )
    out = video_cells_via_map(published, _videos())
    assert int(out.loc[0, "n_judgeable"]) == 1
    assert int(out.loc[0, "n_match"]) == 1
    assert out.loc[0, "stratum"] == "film_pre"
