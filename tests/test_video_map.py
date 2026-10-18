from __future__ import annotations

import pandas as pd
import pytest

from src.run_decomposition import attach_video_groups


def test_attach_video_groups_rejects_a_repeated_video_id() -> None:
    videos = pd.DataFrame(
        {
            "video_id": ["v", "v"],
            "period": ["pre", "post"],
            "film_group": ["film", "other"],
        }
    )
    published = pd.DataFrame({"video_id": ["v"]})
    with pytest.raises(ValueError, match=r"^videos frame has a repeated video_id"):
        attach_video_groups(published, videos)


def test_attach_video_groups_copies_period_and_film_group() -> None:
    videos = pd.DataFrame(
        {
            "video_id": ["v1", "v2"],
            "period": ["pre", "post"],
            "film_group": ["film", "other"],
        }
    )
    published = pd.DataFrame({"video_id": ["v2", "v1", "v2"]})
    out = attach_video_groups(published, videos)
    assert list(out["period"]) == ["post", "pre", "post"]
    assert list(out["film_group"]) == ["other", "film", "other"]
