"""Onset class from jp_default. Missing readings raise; no silent other-bucket."""

from __future__ import annotations

ONSET_MISSING = "onset missing from jp_default"


def parse_onset(jp: str | None) -> str:
    if jp is None or str(jp).strip() == "":
        raise ValueError(ONSET_MISSING)
    body = str(jp).lower().rstrip("0123456789")
    if not body:
        raise ValueError(ONSET_MISSING)
    if body.startswith("ng"):
        return "ng"
    if body.startswith("gw") or body.startswith("kw"):
        return "gw"
    if body.startswith("n"):
        return "n"
    return "other"
