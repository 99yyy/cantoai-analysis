"""Difference vs baseline, comparison ids, BH, inconclusive rows."""

from __future__ import annotations

from typing import Any, Mapping

DIFFERENCE_NEEDS_COMPONENTS = (
    "reported difference must include group and baseline values"
)
COMPARISON_ID_MISSING = "comparison_id missing from declared comparisons"
EXPLORATORY_HAS_PVALUE = "exploratory row must not carry a p-value"
MIN_JUDGEABLE_INCONCLUSIVE = (
    "n_h_judgeable below min_judgeable requires conclusion inconclusive"
)
CI_UNRELIABLE = "G_h below 10 requires ci_unreliable=1"
CLAP_JOIN_BARRED = (
    "clap_sing must not join PANNs singing_prob in the same comparison"
)


def difference_vs_baseline(
    treatment_value,
    treatment_baseline,
    control_value,
    control_baseline,
) -> dict[str, Any]:
    components = (
        treatment_value,
        treatment_baseline,
        control_value,
        control_baseline,
    )
    if any(c is None for c in components):
        raise ValueError(DIFFERENCE_NEEDS_COMPONENTS)
    gap = treatment_value - control_value
    baseline_gap = treatment_baseline - control_baseline
    return {
        "did": gap - baseline_gap,
        "treatment_value": treatment_value,
        "treatment_baseline": treatment_baseline,
        "control_value": control_value,
        "control_baseline": control_baseline,
    }


def require_comparison_id(comparison_id: str, declared: list[str]) -> None:
    if comparison_id not in declared:
        raise ValueError(COMPARISON_ID_MISSING)


def exploratory_row(payload: Mapping[str, Any]) -> None:
    if payload.get("exploratory") == 1:
        if payload.get("p_raw") is not None or payload.get("p_bh") is not None:
            raise ValueError(EXPLORATORY_HAS_PVALUE)


def conclusion_for(
    G_h: int,
    n_h_judgeable: int,
    min_judgeable: int,
) -> dict[str, Any]:
    ci_unreliable = 1 if G_h < 10 else 0
    conclusion = "pending"
    if ci_unreliable == 1 or n_h_judgeable < min_judgeable:
        conclusion = "inconclusive"
    require_ci_unreliable(G_h, ci_unreliable)
    require_inconclusive(n_h_judgeable, min_judgeable, conclusion)
    return {
        "ci_unreliable": ci_unreliable,
        "conclusion": conclusion,
        "n_h_judgeable": n_h_judgeable,
    }


def require_inconclusive(n_h_judgeable: int, min_judgeable: int, conclusion: str) -> None:
    if n_h_judgeable < min_judgeable and conclusion != "inconclusive":
        raise ValueError(MIN_JUDGEABLE_INCONCLUSIVE)


def require_ci_unreliable(G_h: int, ci_unreliable: int) -> None:
    if G_h < 10 and ci_unreliable != 1:
        raise ValueError(CI_UNRELIABLE)


def assert_no_clap_in_comparison(comparison_id: str, columns: list[str]) -> None:
    barred = {"c2_highsnr_onset_residual", "c3_singing_removal"}
    if comparison_id in barred and "clap_sing" in columns:
        raise ValueError(CLAP_JOIN_BARRED)


def bh_corrected(p_raw: list[float], m: int) -> list[float]:
    if m != len(p_raw):
        raise ValueError(COMPARISON_ID_MISSING)
    order = sorted(range(len(p_raw)), key=lambda i: p_raw[i])
    out = [0.0] * len(p_raw)
    prev = 1.0
    for rank_from_end, idx in enumerate(reversed(order)):
        rank = m - rank_from_end
        val = p_raw[idx] * m / rank
        if val > prev:
            val = prev
        if val > 1:
            val = 1.0
        out[idx] = val
        prev = val
    return out
