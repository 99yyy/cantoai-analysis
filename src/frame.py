"""Load frame.yaml and apply declared predicates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

TIER_WHITELIST_MISSING = "tier whitelist predicate missing from published-set filter"
BARRED_STRATIFIER = "barred stratifier used as group or stratum"
BOTH_GROUPS = "row matches both treatment and control"
ACCOUNTING_REQUIRED = "rows dropped must be recorded in row_accounting"

BOILER_TEXT = "如果覺得內容啱睇嘅subscribe"


def load_frame(frame_FILE: str) -> dict[str, Any]:
    path = Path(frame_FILE)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(TIER_WHITELIST_MISSING)
    return raw


def tier_whitelist(frame: dict[str, Any]) -> list[str]:
    allowed = list(frame.get("tier_whitelist") or [])
    if allowed != ["A", "B"]:
        raise ValueError(TIER_WHITELIST_MISSING)
    return allowed


def apply_tier_whitelist(df, frame: dict[str, Any], row_accounting: list[dict[str, Any]]):
    allowed = tier_whitelist(frame)
    if "tier" not in df.columns:
        raise ValueError(TIER_WHITELIST_MISSING)
    before = len(df)
    mask = df["tier"].isin(allowed)
    out = df.loc[mask].copy()
    after = len(out)
    row_accounting.append(
        {
            "step": "tier_whitelist",
            "rule": "windows.tier IN ('A', 'B')",
            "group": "all",
            "rows_before": before,
            "rows_after": after,
        }
    )
    if (~df["tier"].isin(allowed)).any() and after == before:
        raise ValueError(TIER_WHITELIST_MISSING)
    return out


def apply_boiler_exclusion(df, row_accounting: list[dict[str, Any]]):
    if "text_clean" not in df.columns:
        raise ValueError(ACCOUNTING_REQUIRED)
    before = len(df)
    out = df.loc[df["text_clean"] != BOILER_TEXT].copy()
    row_accounting.append(
        {
            "step": "exclude_boiler_trailing",
            "rule": "windows.text_clean != subscribe-boiler",
            "group": "all",
            "rows_before": before,
            "rows_after": len(out),
        }
    )
    return out


def barred_columns(frame: dict[str, Any]) -> set[str]:
    return set(frame.get("barred_stratifiers") or [])


def assert_stratum_column(column: str, frame: dict[str, Any]) -> None:
    if column in barred_columns(frame):
        raise ValueError(BARRED_STRATIFIER)
    treatment = str(frame["groups"]["treatment"]["predicate"])
    control = str(frame["groups"]["control"]["predicate"])
    if column in treatment.split() or column in control.split():
        return
    if column in ("flag_sing", "review_prior", "coverage"):
        raise ValueError(BARRED_STRATIFIER)


def assign_group(film_flag, contemporary_only) -> str:
    treatment = film_flag == 1
    control = contemporary_only == 1
    if treatment and control:
        raise ValueError(BOTH_GROUPS)
    if treatment:
        return "treatment"
    if control:
        return "control"
    return "unassigned"
