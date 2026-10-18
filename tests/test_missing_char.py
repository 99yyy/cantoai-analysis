from __future__ import annotations

import pandas as pd
import pytest

from src.decompose import rare_char_set


def test_rare_char_set_rejects_a_missing_character() -> None:
    syllables = pd.DataFrame({"char": ["字"] * 9 + [None]})
    with pytest.raises(ValueError, match=r"^character is missing"):
        rare_char_set(syllables)


def test_rare_char_set_keeps_a_character_below_frequency_10() -> None:
    syllables = pd.DataFrame({"char": ["字"] * 9 + ["詞"] * 10})
    assert rare_char_set(syllables) == {"字"}
