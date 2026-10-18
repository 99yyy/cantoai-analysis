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


def test_agreement_counts_reject_a_missing_duration() -> None:
    df = pd.DataFrame(
        {
            "jp_realized": ["aa", "bb"],
            "dur": [float("nan"), 0.2],
            "jp_match": ["exact_default", "exact_default"],
        }
    )
    with pytest.raises(ValueError, match=r"^syllable duration is missing"):
        agreement_counts(df)


def test_video_cells_reject_a_missing_duration() -> None:
    published = pd.DataFrame(
        {
            "video_id": ["v1"],
            "jp_realized": ["aa"],
            "dur": [float("nan")],
            "jp_match": ["exact_default"],
            "char": ["字"],
        }
    )
    with pytest.raises(ValueError, match=r"^syllable duration is missing"):
        video_cells_via_map(published, _videos())


def test_nonpositive_duration_stays_out_of_the_judgeable_set() -> None:
    df = pd.DataFrame(
        {
            "jp_realized": ["aa", "bb"],
            "dur": [0.0, 0.2],
            "jp_match": ["exact_default", "exact_default"],
        }
    )
    counts = agreement_counts(df)
    assert counts["n_total"] == 2
    assert counts["n_judgeable"] == 1
    assert counts["n_match"] == 1
    assert counts["n_dur_le_0"] == 1
    assert counts["n_empty_realized"] == 0
    published = pd.DataFrame(
        {
            "video_id": ["v1", "v1"],
            "jp_realized": ["aa", "bb"],
            "dur": [0.0, 0.2],
            "jp_match": ["exact_default", "exact_default"],
            "char": ["字", "詞"],
        }
    )
    out = video_cells_via_map(published, _videos())
    assert int(out.loc[0, "n_judgeable"]) == 1
    assert int(out.loc[0, "n_match"]) == 1
