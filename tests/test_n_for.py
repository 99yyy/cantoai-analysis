from __future__ import annotations

import pytest

from src.write_results import N_FOR, ORDER, n_for

GOT = {
    "n_total_pre": 11,
    "n_total_post": 22,
    "n_judgeable_pre": 33,
    "n_judgeable_post": 44,
    "n_judgeable_film_pre": 55,
    "n_judgeable_film_post": 66,
    "n_judgeable_other_pre": 77,
    "n_judgeable_other_post": 88,
}

EXPECTED = {
    "n_videos_pre": 567,
    "n_videos_post": 567,
    "n_unassigned_period": 567,
    "n_unassigned_film": 567,
    "n_total_pre": 11,
    "n_total_post": 22,
    "n_match_pre": 11,
    "n_match_post": 22,
    "n_empty_realized_pre": 11,
    "n_empty_realized_post": 22,
    "n_dur_le_0_pre": 11,
    "n_dur_le_0_post": 22,
    "n_empty_and_zerodur_pre": 11,
    "n_empty_and_zerodur_post": 22,
    "n_judgeable_pre": 11,
    "n_judgeable_post": 22,
    "n_judgeable_film_pre": 11,
    "n_judgeable_film_post": 22,
    "n_judgeable_other_pre": 11,
    "n_judgeable_other_post": 22,
    "gap_contract_pp": 77,
    "gap_all_pp": 33,
    "gap_excl_none_pp": 33,
    "gap_excl_zerodur_pp": 33,
    "agree_film_pre": 55,
    "agree_film_post": 66,
    "agree_other_pre": 77,
    "agree_other_post": 88,
    "did_film_pp": 286,
    "rare_share_pre": 11,
    "rare_share_post": 22,
    "rate_tone_pre_pm": 11,
    "rate_tone_post_pm": 22,
    "rate_segment_pre_pm": 11,
    "rate_segment_post_pm": 22,
    "rate_diff_pre_pm": 11,
    "rate_diff_post_pm": 22,
    "rate_none_pre_pm": 11,
    "rate_none_post_pm": 22,
}


def test_n_for_matches_the_declared_row_count() -> None:
    assert set(N_FOR) == set(ORDER) == set(EXPECTED)
    for name, count in EXPECTED.items():
        assert n_for(name, GOT, 567) == count


def test_n_for_rejects_a_name_that_only_looks_like_post() -> None:
    with pytest.raises(ValueError, match=r"^n_for received an undeclared number name"):
        n_for("made_up_post", GOT, 567)
    with pytest.raises(ValueError, match=r"^n_for received an undeclared number name"):
        n_for("label_post_pre", GOT, 567)
