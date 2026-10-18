from __future__ import annotations

import pandas as pd
import pytest

from src.run_decomposition import period_rare_share


def test_period_rare_share_rejects_an_empty_group() -> None:
    with pytest.raises(ValueError, match=r"^rare share period group is empty"):
        period_rare_share(pd.Series([], dtype=bool))


def test_period_rare_share_rejects_nan() -> None:
    with pytest.raises(ValueError, match=r"^rare share is NaN"):
        period_rare_share(pd.Series([float("nan")]))


def test_period_rare_share_is_the_mean_of_the_flag() -> None:
    assert period_rare_share(pd.Series([True, False, True, False])) == 0.5
