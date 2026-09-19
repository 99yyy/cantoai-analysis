"""Cluster bootstrap by video_id with per-stratum sha256 seeds."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

STRATA = ("film_pre", "film_post", "other_pre", "other_post")


def stratum_seed(master_seed: int, h: str) -> int:
    payload = f"{master_seed}:{h}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:8], 16)


def make_stratum_seeds(master_seed: int, strata: tuple[str, ...] | list[str]) -> dict[str, int]:
    seeds = {h: stratum_seed(master_seed, h) for h in strata}
    assert_seeds_distinct(seeds)
    return seeds


def assert_seeds_distinct(seeds: dict[str, int]) -> None:
    if len(set(seeds.values())) != len(seeds):
        raise ValueError("bootstrap stratum seeds are not pairwise distinct")


def assert_bootstrap_B(B: int) -> None:
    if B < 1000:
        raise ValueError("bootstrap B is below 1000")


def assert_kitagawa_pre_mix(
    w_film_pre: float,
    w_other_pre: float,
    j_film_pre: float,
    j_other_pre: float,
) -> None:
    total = float(j_film_pre) + float(j_other_pre)
    expected_film = float(j_film_pre) / total
    expected_other = float(j_other_pre) / total
    if (
        abs(float(w_film_pre) - expected_film) > 1e-6
        or abs(float(w_other_pre) - expected_other) > 1e-6
    ):
        raise ValueError(
            "kitagawa pre-mix weights do not equal pre-period judgeable shares"
        )


def video_stratum(film_group: str, period: str) -> str:
    return f"{film_group}_{period}"


def kitagawa_from_stratum_sums(sums: dict[str, tuple[float, float]]) -> dict[str, float]:
    def agr(h: str) -> float:
        n_j, n_m = sums[h]
        return n_m / n_j

    j_pre = sums["film_pre"][0] + sums["other_pre"][0]
    m_pre = sums["film_pre"][1] + sums["other_pre"][1]
    j_post = sums["film_post"][0] + sums["other_post"][0]
    m_post = sums["film_post"][1] + sums["other_post"][1]
    agree_pre = m_pre / j_pre
    agree_post = m_post / j_post
    w_film_pre = sums["film_pre"][0] / j_pre
    w_other_pre = sums["other_pre"][0] / j_pre
    assert_kitagawa_pre_mix(
        w_film_pre, w_other_pre, sums["film_pre"][0], sums["other_pre"][0]
    )
    cf_post = w_film_pre * agr("film_post") + w_other_pre * agr("other_post")
    residual = agree_pre - cf_post
    unadjusted = agree_pre - agree_post
    return {
        "agree_pre": agree_pre,
        "agree_post": agree_post,
        "agree_film_pre": agr("film_pre"),
        "agree_film_post": agr("film_post"),
        "agree_other_pre": agr("other_pre"),
        "agree_other_post": agr("other_post"),
        "w_film_pre": w_film_pre,
        "w_other_pre": w_other_pre,
        "cf_post": cf_post,
        "unadjusted": unadjusted,
        "residual": residual,
        "explained": unadjusted - residual,
        "did": (agr("film_pre") - agr("film_post")) - (agr("other_pre") - agr("other_post")),
    }


def _stratum_index_draws(
    n: int, B: int, rng: np.random.Generator
) -> np.ndarray:
    return rng.integers(0, n, size=(B, n), endpoint=False)


def bootstrap_residual(
    videos: pd.DataFrame,
    B: int,
    master_seed: int,
) -> dict:
    assert_bootstrap_B(B)
    seeds = make_stratum_seeds(master_seed, list(STRATA))
    G_h: dict[str, int] = {}
    draws: dict[str, np.ndarray] = {}
    nj: dict[str, np.ndarray] = {}
    nm: dict[str, np.ndarray] = {}
    for h in STRATA:
        block = videos.loc[videos["stratum"] == h]
        G_h[h] = int(len(block))
        nj[h] = block["n_judgeable"].to_numpy(dtype=float)
        nm[h] = block["n_match"].to_numpy(dtype=float)
        rng = np.random.default_rng(seeds[h])
        draws[h] = _stratum_index_draws(G_h[h], B, rng)

    residual = np.empty(B, dtype=float)
    unadjusted = np.empty(B, dtype=float)
    explained = np.empty(B, dtype=float)
    for b in range(B):
        sums = {}
        for h in STRATA:
            idx = draws[h][b]
            sums[h] = (float(nj[h][idx].sum()), float(nm[h][idx].sum()))
        stats = kitagawa_from_stratum_sums(sums)
        residual[b] = stats["residual"]
        unadjusted[b] = stats["unadjusted"]
        explained[b] = stats["explained"]

    def percentile_ci(x: np.ndarray) -> tuple[float, float]:
        return float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))

    r_lo, r_hi = percentile_ci(residual)
    share_pos = float(np.mean(residual > 0))
    share_neg = float(np.mean(residual < 0))
    p_raw = float(min(1.0, 2.0 * min(share_pos, share_neg)))
    ci_unreliable = {h: int(G_h[h] < 10) for h in STRATA}
    return {
        "B": B,
        "master_seed": master_seed,
        "seeds": seeds,
        "G_h": G_h,
        "ci_unreliable": ci_unreliable,
        "residual_replicates": residual,
        "unadjusted_replicates": unadjusted,
        "explained_replicates": explained,
        "residual_ci95": (r_lo, r_hi),
        "unadjusted_ci95": percentile_ci(unadjusted),
        "explained_ci95": percentile_ci(explained),
        "p_raw": p_raw,
        "p_bh": p_raw,
        "m": 1,
    }


def conclusion_for_ci(ci_unreliable_flags: dict[str, int], G_h: dict[str, int]) -> str:
    if any(ci_unreliable_flags.values()):
        actual = {h: G_h[h] for h, flag in ci_unreliable_flags.items() if flag}
        _ = actual
        return "inconclusive"
    return "estimated"


def assert_inconclusive_when_unreliable(ci_unreliable: int, conclusion: str) -> None:
    if ci_unreliable == 1 and conclusion != "inconclusive":
        raise ValueError("ci_unreliable row must carry conclusion=inconclusive")
