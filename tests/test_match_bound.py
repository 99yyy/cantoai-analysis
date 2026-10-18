from __future__ import annotations

import pandas as pd
import pytest

from src.measures import attach_agreement


def test_attach_agreement_rejects_more_matches_than_judgeable() -> None:
    df = pd.DataFrame({"n_judgeable": [10], "n_match": [12]})
    with pytest.raises(ValueError, match=r"^n_match exceeds n_judgeable"):
        attach_agreement(df)


def test_attach_agreement_keeps_a_rate_inside_the_judgeable_count() -> None:
    df = pd.DataFrame({"n_judgeable": [10, 0], "n_match": [8, 0]})
    out = attach_agreement(df)
    assert out.loc[0, "agreement_status"] == "ok"
    assert float(out.loc[0, "agreement"]) == 0.8
    assert out.loc[1, "agreement_status"] == "missing"
    assert pd.isna(out.loc[1, "agreement"])
