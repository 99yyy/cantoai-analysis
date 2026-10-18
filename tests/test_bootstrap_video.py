from __future__ import annotations

import pandas as pd
import pytest

from src.bootstrap import bootstrap_residual

STRATA = ("film_pre", "film_post", "other_pre", "other_post")


def _frame(video_ids: list[str]) -> pd.DataFrame:
    rows = []
    for video_id, stratum in zip(video_ids, STRATA * 2):
        rows.append(
            {
                "video_id": video_id,
                "stratum": stratum,
                "n_judgeable": 4.0,
                "n_match": 2.0,
            }
        )
    return pd.DataFrame(rows)


def test_bootstrap_rejects_a_repeated_video_id() -> None:
    videos = _frame(["v0", "v1", "v2", "v0"])
    with pytest.raises(ValueError, match=r"^bootstrap rows are not one per video_id"):
        bootstrap_residual(videos, 1000, 20250918)


def test_bootstrap_runs_when_each_row_is_one_video_id() -> None:
    videos = _frame(["v0", "v1", "v2", "v3"])
    boot = bootstrap_residual(videos, 1000, 20250918)
    assert boot["G_h"] == {h: 1 for h in STRATA}
    assert boot["ci_unreliable"] == {h: 1 for h in STRATA}
