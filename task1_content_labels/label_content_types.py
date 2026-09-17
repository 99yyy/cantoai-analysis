#!/usr/bin/env python3
"""Task 1: label videos by title keywords and report agreement by content_type.

Agreement = share of syllables with jp_match in {exact_default, exact_alt}.
Primary scope: tiers A+B (syllables.tier).
Bootstrap: resample by video_id, B=2000, 95% percentile CI.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sqlite3

ROOT = Path("/workspace/cantoai")
DB = ROOT / "corpus/dataset_v2/work/corpus.sqlite"
OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

EXACT = {"exact_default", "exact_alt"}
RNG_SEED = 20260917
N_BOOT = 2000

# ---------------------------------------------------------------------------
# Keyword rules (hard-coded; same set used for README and outputs)
# Priority on conflict (first match wins):
#   parody > song > recitation > film_clip > contemporary
# ---------------------------------------------------------------------------
KEYWORDS = {
    "parody": [
        "惡搞",
        "配音",
    ],
    "song": [
        "主題曲",
        "插曲",
        "粵曲",
        # supplements
        "經典金曲",
        "翻唱",
        "清唱",
        "獻唱",
        "主唱",
        "合唱",
    ],
    "recitation": [
        "朗誦",
        # supplements: corpus titles use 誦讀 / 朗讀, never 朗誦
        "誦讀",
        "朗讀",
    ],
    "film_clip": [
        # required mid-century / classic cinema markers
        "李小龍",
        "任劍輝",
        "芳艷芬",
        "林鳳",
        "吳楚帆",
        "石堅",
        "謝賢",
        "粵劇",
        # supplements (classic HK cinema / 粵語片 markers; do not include
        # modern celebrities or song/parody terms)
        "粵語長片",
        "粵語片",
        "戲曲",
        "銀幕",
        "影星",
        "白雪仙",
        "新馬師曾",
        "紅線女",
        "唐滌生",
        "夏夢",
        "于素秋",
        "張活游",
        "白燕",
        "紫羅蓮",
        "林黛",
        "嘉玲",
        "李龍基",
        "王青霞",
    ],
}

# PIPELINE.md "film-related" proxy: the eight required film markers alone.
# Used only for the expected-control comparison (119 videos / ~24% A+B syllables).
FILM_RELATED_CORE = [
    "李小龍",
    "任劍輝",
    "芳艷芬",
    "林鳳",
    "吳楚帆",
    "石堅",
    "謝賢",
    "粵劇",
]

PRIORITY = ["parody", "song", "recitation", "film_clip"]
CONTENT_ORDER = ["parody", "song", "recitation", "film_clip", "contemporary"]


def has_any(title: str, keywords: list[str]) -> bool:
    t = title or ""
    return any(k in t for k in keywords)


def matched_keywords(title: str, keywords: list[str]) -> str:
    t = title or ""
    hits = [k for k in keywords if k in t]
    return "|".join(hits)


def label_title(title: str) -> tuple[str, str]:
    """Return (content_type, matched_keywords_pipe)."""
    t = title or ""
    for ctype in PRIORITY:
        hits = matched_keywords(t, KEYWORDS[ctype])
        if hits:
            return ctype, hits
    return "contemporary", ""


def agreement_rate(jp_match: pd.Series) -> float:
    if len(jp_match) == 0:
        return float("nan")
    return float(jp_match.isin(EXACT).mean())


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(DB)
    videos = pd.read_sql_query(
        "SELECT video_id, title, upload_date, n_windows, speech_s FROM videos", con
    )
    windows = pd.read_sql_query("SELECT uid, video_id, tier FROM windows", con)
    syllables = pd.read_sql_query(
        "SELECT syl_id, uid, video_id, tier, jp_match FROM syllables", con
    )
    con.close()
    return videos, windows, syllables


def bootstrap_agreement_by_video(
    syl: pd.DataFrame,
    video_ids: np.ndarray,
    n_boot: int = N_BOOT,
    seed: int = RNG_SEED,
) -> tuple[float, float, float]:
    """Syllable-weighted agreement CI via video_id resampling.

    Each bootstrap draw: sample video_ids with replacement, concatenate all
    their syllables, compute agreement. Returns (point, ci_lo, ci_hi).
    Point estimate is on the original (non-resampled) syllable set.
    """
    if len(syl) == 0 or len(video_ids) == 0:
        return float("nan"), float("nan"), float("nan")

    point = agreement_rate(syl["jp_match"])
    by_vid = {vid: g["jp_match"].to_numpy() for vid, g in syl.groupby("video_id")}
    vids = np.asarray(list(by_vid.keys()))
    if len(vids) == 0:
        return point, float("nan"), float("nan")

    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        sample = rng.choice(vids, size=len(vids), replace=True)
        parts = [by_vid[v] for v in sample]
        pooled = np.concatenate(parts)
        boots[b] = float(np.isin(pooled, list(EXACT)).mean()) if len(pooled) else np.nan

    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi)


def bootstrap_diff_vs_control(
    syl_group: pd.DataFrame,
    syl_control: pd.DataFrame,
    n_boot: int = N_BOOT,
    seed: int = RNG_SEED,
) -> tuple[float, float, float]:
    """Difference in agreement (group - control), video-resampled within each arm."""
    if len(syl_group) == 0 or len(syl_control) == 0:
        return float("nan"), float("nan"), float("nan")

    point = agreement_rate(syl_group["jp_match"]) - agreement_rate(syl_control["jp_match"])
    by_g = {vid: g["jp_match"].to_numpy() for vid, g in syl_group.groupby("video_id")}
    by_c = {vid: g["jp_match"].to_numpy() for vid, g in syl_control.groupby("video_id")}
    vids_g = np.asarray(list(by_g.keys()))
    vids_c = np.asarray(list(by_c.keys()))
    if len(vids_g) == 0 or len(vids_c) == 0:
        return point, float("nan"), float("nan")

    rng = np.random.default_rng(seed + 1)
    boots = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        sg = np.concatenate([by_g[v] for v in rng.choice(vids_g, size=len(vids_g), replace=True)])
        sc = np.concatenate([by_c[v] for v in rng.choice(vids_c, size=len(vids_c), replace=True)])
        ag = float(np.isin(sg, list(EXACT)).mean()) if len(sg) else np.nan
        ac = float(np.isin(sc, list(EXACT)).mean()) if len(sc) else np.nan
        boots[b] = ag - ac

    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi)


def main() -> None:
    videos, windows, syllables = load()

    labels = videos["title"].map(label_title)
    videos = videos.copy()
    videos["content_type"] = [x[0] for x in labels]
    videos["matched_keywords"] = [x[1] for x in labels]
    videos["film_related_core"] = videos["title"].map(
        lambda t: has_any(t, FILM_RELATED_CORE)
    )

    # Per-video A+B counts for the label table
    syl_ab = syllables[syllables["tier"].isin(["A", "B"])].copy()
    win_ab = windows[windows["tier"].isin(["A", "B"])].copy()

    syl_counts = (
        syl_ab.groupby("video_id")
        .agg(
            n_syllables_AB=("jp_match", "size"),
            n_exact_AB=("jp_match", lambda s: int(s.isin(EXACT).sum())),
        )
        .reset_index()
    )
    win_counts = win_ab.groupby("video_id").size().rename("n_windows_AB").reset_index()

    video_labels = videos.merge(syl_counts, on="video_id", how="left").merge(
        win_counts, on="video_id", how="left"
    )
    video_labels["n_syllables_AB"] = video_labels["n_syllables_AB"].fillna(0).astype(int)
    video_labels["n_exact_AB"] = video_labels["n_exact_AB"].fillna(0).astype(int)
    video_labels["n_windows_AB"] = video_labels["n_windows_AB"].fillna(0).astype(int)
    video_labels["agreement_AB"] = np.where(
        video_labels["n_syllables_AB"] > 0,
        video_labels["n_exact_AB"] / video_labels["n_syllables_AB"],
        np.nan,
    )
    video_labels = video_labels.sort_values("video_id")
    video_labels.to_csv(OUT / "video_labels.csv", index=False)

    # Attach content_type to syllables / windows
    vt = video_labels.set_index("video_id")["content_type"]
    syl_ab = syl_ab.copy()
    syl_ab["content_type"] = syl_ab["video_id"].map(vt)
    win_ab = win_ab.copy()
    win_ab["content_type"] = win_ab["video_id"].map(vt)

    control = syl_ab[syl_ab["content_type"] == "contemporary"]

    rows = []
    for ctype in CONTENT_ORDER:
        vids = video_labels[video_labels["content_type"] == ctype]
        sg = syl_ab[syl_ab["content_type"] == ctype]
        wg = win_ab[win_ab["content_type"] == ctype]
        point, lo, hi = bootstrap_agreement_by_video(
            sg, vids["video_id"].to_numpy(), n_boot=N_BOOT, seed=RNG_SEED
        )
        if ctype == "contemporary":
            d_point = d_lo = d_hi = float("nan")
        else:
            d_point, d_lo, d_hi = bootstrap_diff_vs_control(
                sg, control, n_boot=N_BOOT, seed=RNG_SEED
            )
        rows.append(
            {
                "content_type": ctype,
                "n_videos": int(len(vids)),
                "n_windows_AB": int(wg["uid"].nunique()) if len(wg) else 0,
                "n_syllables_AB": int(len(sg)),
                "share_syllables_AB": float(len(sg) / len(syl_ab)) if len(syl_ab) else np.nan,
                "agreement_AB": point,
                "agreement_ci_lo": lo,
                "agreement_ci_hi": hi,
                "delta_vs_contemporary": d_point,
                "delta_ci_lo": d_lo,
                "delta_ci_hi": d_hi,
                "n_boot": N_BOOT,
                "boot_seed": RNG_SEED,
            }
        )

    # Extra row: PIPELINE film-related core (keyword hit, no priority reclass)
    core_vids = video_labels[video_labels["film_related_core"]]
    core_syl = syl_ab[syl_ab["video_id"].isin(core_vids["video_id"])]
    core_win = win_ab[win_ab["video_id"].isin(core_vids["video_id"])]
    c_point, c_lo, c_hi = bootstrap_agreement_by_video(
        core_syl, core_vids["video_id"].to_numpy(), n_boot=N_BOOT, seed=RNG_SEED
    )
    d_point, d_lo, d_hi = bootstrap_diff_vs_control(
        core_syl,
        syl_ab[~syl_ab["video_id"].isin(core_vids["video_id"])],
        n_boot=N_BOOT,
        seed=RNG_SEED,
    )
    rows.append(
        {
            "content_type": "film_related_core_PIPELINE",
            "n_videos": int(len(core_vids)),
            "n_windows_AB": int(core_win["uid"].nunique()) if len(core_win) else 0,
            "n_syllables_AB": int(len(core_syl)),
            "share_syllables_AB": float(len(core_syl) / len(syl_ab)) if len(syl_ab) else np.nan,
            "agreement_AB": c_point,
            "agreement_ci_lo": c_lo,
            "agreement_ci_hi": c_hi,
            "delta_vs_contemporary": d_point,  # here: vs non-core (PIPELINE contrast)
            "delta_ci_lo": d_lo,
            "delta_ci_hi": d_hi,
            "n_boot": N_BOOT,
            "boot_seed": RNG_SEED,
        }
    )

    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "summary_by_content_type.csv", index=False)

    # --- Plots ---
    plot_df = summary[summary["content_type"].isin(CONTENT_ORDER)].copy()
    plot_df["content_type"] = pd.Categorical(
        plot_df["content_type"], categories=CONTENT_ORDER, ordered=True
    )
    plot_df = plot_df.sort_values("content_type")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    ax = axes[0]
    x = np.arange(len(plot_df))
    y = plot_df["agreement_AB"].to_numpy()
    yerr = np.vstack(
        [
            y - plot_df["agreement_ci_lo"].to_numpy(),
            plot_df["agreement_ci_hi"].to_numpy() - y,
        ]
    )
    colors = ["#E45756", "#F58518", "#54A24B", "#4C78A8", "#9D755D"]
    ax.bar(x, y, color=colors, yerr=yerr, capsize=4, ecolor="#333333")
    ax.set_xticks(x)
    ax.set_xticklabels(plot_df["content_type"], rotation=20, ha="right")
    ax.set_ylim(0.55, 1.0)
    ax.set_ylabel("Agreement (exact_default + exact_alt)")
    ax.set_title("A+B agreement by content_type\n(video-resampled 95% CI, B=2000)")
    for i, r in enumerate(plot_df.itertuples()):
        ax.text(
            i,
            r.agreement_AB + 0.02,
            f"{r.agreement_AB:.3f}\nn={r.n_syllables_AB}",
            ha="center",
            va="bottom",
            fontsize=7,
        )

    ax = axes[1]
    shares = plot_df["n_syllables_AB"].to_numpy()
    labels_pie = [
        f"{ct}\n{n_v} vids / {share:.1%}"
        for ct, n_v, share in zip(
            plot_df["content_type"], plot_df["n_videos"], plot_df["share_syllables_AB"]
        )
    ]
    ax.pie(
        shares,
        labels=labels_pie,
        colors=colors,
        startangle=90,
        textprops={"fontsize": 8},
    )
    ax.set_title("A+B syllable share by content_type")

    fig.tight_layout()
    fig.savefig(OUT / "agreement_by_content_type.png", dpi=150)
    plt.close(fig)

    # Console summary
    print("=== SUMMARY (A+B) ===")
    print(
        summary[
            [
                "content_type",
                "n_videos",
                "n_windows_AB",
                "n_syllables_AB",
                "share_syllables_AB",
                "agreement_AB",
                "agreement_ci_lo",
                "agreement_ci_hi",
                "delta_vs_contemporary",
                "delta_ci_lo",
                "delta_ci_hi",
            ]
        ].to_string(index=False)
    )
    print("\nWrote outputs to", OUT)


if __name__ == "__main__":
    main()
