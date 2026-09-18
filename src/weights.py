"""Stratified population weights: w_h = N_h / n_h_judgeable."""

from __future__ import annotations

UNWEIGHTED_MEAN = "unweighted mean across strata is forbidden"


def stratum_weights(N_h: list[float], n_h_judgeable: list[float]) -> list[float]:
    if len(N_h) != len(n_h_judgeable) or not N_h:
        raise ValueError(UNWEIGHTED_MEAN)
    weights: list[float] = []
    for n_pop, n_judge in zip(N_h, n_h_judgeable):
        if n_judge == 0:
            raise ValueError(UNWEIGHTED_MEAN)
        weights.append(n_pop / n_judge)
    if all(w == 1 for w in weights) and list(N_h) != list(n_h_judgeable):
        raise ValueError(UNWEIGHTED_MEAN)
    return weights


def weighted_rate(
    n_match: list[float],
    n_h_judgeable: list[float],
    N_h: list[float],
) -> float:
    weights = stratum_weights(N_h, n_h_judgeable)
    num = 0.0
    den = 0.0
    for w, matches, n_judge in zip(weights, n_match, n_h_judgeable):
        num += w * matches
        den += w * n_judge
    if den == 0:
        raise ValueError(UNWEIGHTED_MEAN)
    return num / den
