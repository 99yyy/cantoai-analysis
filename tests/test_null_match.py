from __future__ import annotations

import pandas as pd
import pytest

from src.agreement import agreement_counts
from src.decompose import video_cells_via_map


def _videos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "video_id": ["v1"],
            "period": ["pre"],
            "film_group": ["film"],
        }
    )


def test_video_cells_reject_null_jp_match_on_a_judgeable_syllable() -> None:
    published = pd.DataFrame(
        {
            "video_id": ["v1"],
            "jp_realized": ["aa"],
            "dur": [0.2],
            "jp_match": [None],
            "char": ["字"],
        }
    )
    with pytest.raises(ValueError, match=r"^judgeable syllable has NULL jp_match"):
        video_cells_via_map(published, _videos())
    with pytest.raises(ValueError, match=r"^judgeable syllable has NULL jp_match"):
        agreement_counts(published)


def test_video_cells_keep_a_real_match_and_a_real_non_match() -> None:
    published = pd.DataFrame(
        {
            "video_id": ["v1", "v1", "v1"],
            "jp_realized": ["aa", "bb", None],
            "dur": [0.2, 0.2, 0.0],
            "jp_match": ["exact_default", "tone", None],
            "char": ["字", "詞", "句"],
        }
    )
    out = video_cells_via_map(published, _videos())
    assert int(out.loc[0, "n_judgeable"]) == 2
    assert int(out.loc[0, "n_match"]) == 1
    assert out.loc[0, "stratum"] == "film_pre"
