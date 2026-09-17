"""Jyutping onset / coda / tone parsing for stratified agreement.

Dictionary readings come from ``jp_default`` (fallback ``jp_ctx``).
Tone digits are stripped before onset/coda classification.

Onset (声母) rules, longest-match first:
  - ng-   velar nasal 疑母
  - gw-/kw-  labialized velars 合口見組
  - n-    泥母 (after ng- so ``ngaa`` is not n-)
  - l-    來母
  - g-/k- 見組 without labialization (after gw-/kw-)
  - zero  vowel [aeiou] or glide j-/w-
  - other remaining initials (b p m f d t s z c h …)

Coda (韵尾) rules, longest-match first:
  - -ng, -n, -t, -k, -p, -m, else open (no coda)

Tone: last digit 1–6 on the jyutping string; 0 if missing/invalid.
"""
from __future__ import annotations

import pandas as pd


def _strip_tone(jp: str) -> str:
    return jp.lower().rstrip("0123456")


def parse_initial(jp: str | None) -> str:
    """Classify a jyutping syllable's initial (声母). See module docstring."""
    if not jp or not isinstance(jp, str):
        return "other"

    jp_clean = _strip_tone(jp)
    if not jp_clean:
        return "other"

    if jp_clean.startswith("ng"):
        return "ng-"
    if jp_clean.startswith("gw") or jp_clean.startswith("kw"):
        return "gw-/kw-"
    if jp_clean.startswith("n"):
        return "n-"
    if jp_clean.startswith("l"):
        return "l-"
    if jp_clean.startswith("g") or jp_clean.startswith("k"):
        return "g-/k-"
    if jp_clean[0] in "aeiou" or jp_clean.startswith("j") or jp_clean.startswith("w"):
        return "zero"
    return "other"


def parse_coda(jp: str | None) -> str:
    """Classify a jyutping syllable's coda (韵尾). See module docstring."""
    if not jp or not isinstance(jp, str):
        return "open"

    jp_clean = _strip_tone(jp)
    if not jp_clean:
        return "open"

    if jp_clean.endswith("ng"):
        return "-ng"
    if jp_clean.endswith("n"):
        return "-n"
    if jp_clean.endswith("t"):
        return "-t"
    if jp_clean.endswith("k"):
        return "-k"
    if jp_clean.endswith("p"):
        return "-p"
    if jp_clean.endswith("m"):
        return "-m"
    return "open"


def parse_tone(jp: str | None) -> int:
    """Extract tone 1–6 from a jyutping string; 0 if none."""
    if not jp or not isinstance(jp, str):
        return 0
    for c in jp[::-1]:
        if c.isdigit():
            tone = int(c)
            if 1 <= tone <= 6:
                return tone
            return 0
    return 0


def dictionary_jyutping(df: pd.DataFrame) -> pd.Series:
    """Prefer ``jp_default``, fall back to ``jp_ctx`` when default is missing."""
    default = df["jp_default"].astype("string")
    if "jp_ctx" not in df.columns:
        return default
    ctx = df["jp_ctx"].astype("string")
    missing = default.isna() | (default.str.strip() == "")
    return default.where(~missing, ctx)
