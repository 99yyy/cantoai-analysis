from __future__ import annotations

import pytest

from src.bootstrap import kitagawa_from_stratum_sums

ZERO_POST = {
    "film_pre": (10.0, 8.0),
    "film_post": (0.0, 0.0),
    "other_pre": (30.0, 24.0),
    "other_post": (20.0, 16.0),
}

POSITIVE = {
    "film_pre": (10.0, 8.0),
    "film_post": (10.0, 7.0),
    "other_pre": (30.0, 24.0),
    "other_post": (20.0, 16.0),
}


def test_kitagawa_rejects_a_zero_judgeable_stratum() -> None:
    with pytest.raises(ValueError, match=r"^kitagawa stratum judgeable count is zero"):
        kitagawa_from_stratum_sums(ZERO_POST)
    zero_pre = dict(POSITIVE)
    zero_pre["film_pre"] = (0.0, 0.0)
    with pytest.raises(ValueError, match=r"^kitagawa stratum judgeable count is zero"):
        kitagawa_from_stratum_sums(zero_pre)


def test_kitagawa_keeps_the_pre_mix_when_every_stratum_is_positive() -> None:
    point = kitagawa_from_stratum_sums(POSITIVE)
    assert point["w_film_pre"] == 0.25
    assert point["w_other_pre"] == 0.75
