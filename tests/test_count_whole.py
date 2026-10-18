from __future__ import annotations

import pytest

from src.write_results import json_num


def test_json_num_rejects_a_fractional_count() -> None:
    with pytest.raises(ValueError, match=r"^count result is not a whole number"):
        json_num("n_total", 10.4)


def test_json_num_rejects_a_nan_count() -> None:
    with pytest.raises(ValueError, match=r"^count result is not a whole number"):
        json_num("n_total", float("nan"))


def test_json_num_keeps_a_whole_count_and_a_rate() -> None:
    assert json_num("n_total", 10.0) == 10
    assert json_num("n_total", 10) == 10
    assert json_num("gap_all_pp", 10.4) == 10.4
