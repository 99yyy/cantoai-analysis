from __future__ import annotations

import pytest

from src.write_results import n_for


def test_n_for_rejects_a_fractional_count() -> None:
    with pytest.raises(ValueError, match=r"^count result is not a whole number"):
        n_for("agree_film_pre", {"n_judgeable_film_pre": 10.4}, 567)


def test_n_for_rejects_a_fractional_sum() -> None:
    got = {"n_judgeable_pre": 10.4, "n_judgeable_post": 1.0}
    with pytest.raises(ValueError, match=r"^count result is not a whole number"):
        n_for("gap_contract_pp", got, 567)


def test_n_for_keeps_a_whole_count() -> None:
    assert n_for("agree_film_pre", {"n_judgeable_film_pre": 10.0}, 567) == 10
    assert n_for("agree_film_pre", {"n_judgeable_film_pre": 10}, 567) == 10
    assert n_for(
        "gap_contract_pp",
        {"n_judgeable_pre": 10, "n_judgeable_post": 2},
        567,
    ) == 12
    assert n_for("n_videos_pre", {}, 567) == 567
