"""Agreement counts from jp_match. Missing values propagate; no sentinels."""

from __future__ import annotations

from typing import Any, Mapping

NULL_JP_MATCH = "NULL jp_match on judgeable row"
STATUS_OK_REQUIRES_DATA = "status ok requires non-null measure computed from data"

MATCH_VALUES = ("exact_default", "exact_alt")
SENTINELS = (0, -1, 999, 9999)

MEASURE_COLUMNS = (
    "n_total",
    "n_match",
    "n_judgeable",
    "n_empty_realized",
    "n_dur_le_0",
    "agreement",
    "did",
    "delta_pp",
    "singing_prob",
    "snr_db",
)

INPUT_COLUMNS = (
    "jp_match",
    "jp_realized",
    "dur",
    "singing_prob",
    "snr_db",
)


def is_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        import math

        if math.isnan(value):
            return True
    return False


def status_for_measure(value: Any, *, computed_from_data: bool) -> str:
    if computed_from_data and not is_null(value):
        return "ok"
    if not is_null(value) and value in SENTINELS:
        raise ValueError(STATUS_OK_REQUIRES_DATA)
    if not is_null(value) and not computed_from_data:
        raise ValueError(STATUS_OK_REQUIRES_DATA)
    return "missing"


def _null_measures() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in MEASURE_COLUMNS:
        out[col] = None
        out[f"{col}_status"] = "missing"
    return out


def _dur_of(row: Mapping[str, Any]) -> Any:
    if "dur" in row:
        return row["dur"]
    return row.get("syllable_dur")


def row_measures(row: Mapping[str, Any]) -> dict[str, Any]:
    """Derive measure columns for one syllable row.

    Any null input column nulls every derived measure in the row (status not
    ok), except a null jp_match on a still-judgeable row, which raises.
    """
    dur = _dur_of(row)
    jp_realized = row.get("jp_realized") if "jp_realized" in row else None
    jp_match = row.get("jp_match") if "jp_match" in row else None

    dur_known = ("dur" in row or "syllable_dur" in row) and not is_null(dur)
    realized_known = "jp_realized" in row
    empty = None
    if realized_known:
        empty = is_null(jp_realized) or str(jp_realized) == ""
    dur_le_0 = None
    if dur_known:
        dur_le_0 = float(dur) <= 0

    judgeable = False
    if empty is not None and dur_le_0 is not None:
        judgeable = (not empty) and (not dur_le_0)
        if judgeable and is_null(jp_match):
            raise ValueError(NULL_JP_MATCH)

    input_null = False
    for col, value in row.items():
        if col == "jp_match":
            continue
        if is_null(value):
            input_null = True

    if input_null or empty is None or dur_le_0 is None:
        return _null_measures()

    n_total = 1
    n_empty = int(empty)
    n_dur = int(dur_le_0)
    n_judgeable = int(judgeable)
    if judgeable:
        n_match = int(jp_match in MATCH_VALUES)
        agreement = n_match / n_judgeable
    else:
        n_match = None
        agreement = None

    singing = row.get("singing_prob")
    snr = row.get("snr_db")
    out: dict[str, Any] = {
        "n_total": n_total,
        "n_empty_realized": n_empty,
        "n_dur_le_0": n_dur,
        "n_judgeable": n_judgeable,
        "n_match": n_match,
        "agreement": agreement,
        "did": None,
        "delta_pp": None,
        "singing_prob": None if is_null(singing) else singing,
        "snr_db": None if is_null(snr) else snr,
    }
    out["n_total_status"] = status_for_measure(n_total, computed_from_data=True)
    out["n_empty_realized_status"] = status_for_measure(n_empty, computed_from_data=True)
    out["n_dur_le_0_status"] = status_for_measure(n_dur, computed_from_data=True)
    out["n_judgeable_status"] = status_for_measure(n_judgeable, computed_from_data=True)
    out["n_match_status"] = status_for_measure(
        n_match, computed_from_data=n_match is not None
    )
    out["agreement_status"] = status_for_measure(
        agreement, computed_from_data=agreement is not None
    )
    out["did_status"] = status_for_measure(None, computed_from_data=False)
    out["delta_pp_status"] = status_for_measure(None, computed_from_data=False)
    out["singing_prob_status"] = status_for_measure(
        out["singing_prob"], computed_from_data=not is_null(out["singing_prob"])
    )
    out["snr_db_status"] = status_for_measure(
        out["snr_db"], computed_from_data=not is_null(out["snr_db"])
    )
    for col in MEASURE_COLUMNS:
        ok = out[f"{col}_status"] == "ok"
        present = not is_null(out[col])
        if ok != present:
            raise ValueError(STATUS_OK_REQUIRES_DATA)
    return out
