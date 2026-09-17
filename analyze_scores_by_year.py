#!/usr/bin/env python3
"""iCantonese corpus quality analysis: agreement (score) by upload year.

Reproducible analysis for FYP dataset investigation.
Score / agreement = share of syllables where jp_match in {exact_default, exact_alt}.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sqlite3

ROOT = Path("/workspace/cantoai")
DB = ROOT / "corpus/dataset_v2/work/corpus.sqlite"
OUT = ROOT / "analysis"
OUT.mkdir(parents=True, exist_ok=True)

EXACT = {"exact_default", "exact_alt"}


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(DB)
    videos = pd.read_sql_query("SELECT * FROM videos", con)
    windows = pd.read_sql_query("SELECT * FROM windows", con)
    syllables = pd.read_sql_query(
        "SELECT syl_id, uid, video_id, pos, char, start, end, dur, tier, "
        "jp_default, jp_ctx, jp_realized, jp_match, review_prior, "
        "verification_status FROM syllables",
        con,
    )
    con.close()
    return videos, windows, syllables


def parse_dates(videos: pd.DataFrame) -> pd.DataFrame:
    v = videos.copy()
    v["upload_date"] = v["upload_date"].astype(str).str.strip()
    v["upload_dt"] = pd.to_datetime(v["upload_date"], format="%Y%m%d", errors="coerce")
    v["year"] = v["upload_dt"].dt.year
    v["period"] = np.where(
        v["upload_dt"].isna(),
        "missing_date",
        np.where(v["upload_dt"] >= "2025-01-01", "2025+", "pre-2025"),
    )
    return v


def agreement_rate(s: pd.Series) -> float:
    if len(s) == 0:
        return float("nan")
    return float(s.isin(EXACT).mean())


def summarize(group: pd.DataFrame, score_col: str = "jp_match") -> dict:
    s = group[score_col]
    exact = s.isin(EXACT)
    return {
        "n_syllables": int(len(s)),
        "n_exact": int(exact.sum()),
        "mean_agreement": float(exact.mean()) if len(s) else np.nan,
        "exact_default_share": float((s == "exact_default").mean()) if len(s) else np.nan,
        "exact_alt_share": float((s == "exact_alt").mean()) if len(s) else np.nan,
        "tone_share": float((s == "tone").mean()) if len(s) else np.nan,
        "segment_share": float((s == "segment").mean()) if len(s) else np.nan,
        "diff_share": float((s == "diff").mean()) if len(s) else np.nan,
        "none_share": float((s == "none").mean()) if len(s) else np.nan,
    }


def video_level_scores(syl: pd.DataFrame, videos: pd.DataFrame) -> pd.DataFrame:
    g = (
        syl.groupby("video_id")
        .agg(
            n_syllables=("jp_match", "size"),
            mean_agreement=("jp_match", lambda x: float(x.isin(EXACT).mean())),
            n_exact=("jp_match", lambda x: int(x.isin(EXACT).sum())),
        )
        .reset_index()
    )
    out = videos.merge(g, on="video_id", how="left")
    out["n_syllables"] = out["n_syllables"].fillna(0).astype(int)
    return out


def main() -> None:
    videos, windows, syllables = load()
    videos = parse_dates(videos)

    # Join upload date onto syllables
    syl = syllables.merge(
        videos[["video_id", "title", "upload_date", "upload_dt", "year", "period"]],
        on="video_id",
        how="left",
    )
    win = windows.merge(
        videos[["video_id", "upload_date", "upload_dt", "year", "period"]],
        on="video_id",
        how="left",
    )

    # --- Schema / inventory ---
    schema = {
        "tables": {
            "videos": list(videos.columns),
            "windows": list(windows.columns),
            "syllables": list(syllables.columns),
        },
        "n_videos": int(len(videos)),
        "n_windows": int(len(windows)),
        "n_syllables": int(len(syllables)),
        "tier_counts_syllables": syllables["tier"].value_counts(dropna=False).to_dict(),
        "tier_counts_windows": windows["tier"].value_counts(dropna=False).to_dict(),
        "jp_match_counts": syllables["jp_match"].value_counts(dropna=False).to_dict(),
        "upload_date_null": int(videos["upload_dt"].isna().sum()),
        "year_range": [
            None if videos["year"].isna().all() else int(videos["year"].min()),
            None if videos["year"].isna().all() else int(videos["year"].max()),
        ],
    }
    (OUT / "schema_summary.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Focus on A+B (published export) and also all tiers
    syl_ab = syl[syl["tier"].isin(["A", "B"])].copy()
    syl_all = syl.copy()

    # --- By year (syllable-weighted agreement) ---
    rows = []
    for label, df in [("AB", syl_ab), ("ALL", syl_all)]:
        for year, g in df.groupby("year", dropna=False):
            r = summarize(g)
            r["scope"] = label
            r["year"] = None if pd.isna(year) else int(year)
            r["n_videos"] = int(g["video_id"].nunique())
            r["n_windows"] = int(g["uid"].nunique())
            rows.append(r)
    by_year = pd.DataFrame(rows).sort_values(["scope", "year"])
    by_year.to_csv(OUT / "agreement_by_year.csv", index=False)

    # --- By period pre-2025 vs 2025+ ---
    rows = []
    for label, df in [("AB", syl_ab), ("ALL", syl_all)]:
        for period, g in df.groupby("period"):
            r = summarize(g)
            r["scope"] = label
            r["period"] = period
            r["n_videos"] = int(g["video_id"].nunique())
            r["n_windows"] = int(g["uid"].nunique())
            rows.append(r)
    by_period = pd.DataFrame(rows).sort_values(["scope", "period"])
    by_period.to_csv(OUT / "agreement_by_period.csv", index=False)

    # Effect size: difference in mean agreement
    ab_pre = syl_ab[syl_ab["period"] == "pre-2025"]
    ab_post = syl_ab[syl_ab["period"] == "2025+"]
    mean_pre = agreement_rate(ab_pre["jp_match"])
    mean_post = agreement_rate(ab_post["jp_match"])
    # Video-level median (unweighted by syllables)
    vscores = video_level_scores(syl_ab, videos)
    v_pre = vscores[(vscores["period"] == "pre-2025") & (vscores["n_syllables"] > 0)]
    v_post = vscores[(vscores["period"] == "2025+") & (vscores["n_syllables"] > 0)]

    effect = {
        "syllable_weighted_mean_agreement_AB": {
            "pre_2025": mean_pre,
            "post_2025": mean_post,
            "delta_post_minus_pre": mean_post - mean_pre,
            "n_syl_pre": int(len(ab_pre)),
            "n_syl_post": int(len(ab_post)),
            "n_videos_pre": int(ab_pre["video_id"].nunique()),
            "n_videos_post": int(ab_post["video_id"].nunique()),
        },
        "video_level_median_agreement_AB": {
            "pre_2025": float(v_pre["mean_agreement"].median()),
            "post_2025": float(v_post["mean_agreement"].median()),
            "delta_post_minus_pre": float(
                v_post["mean_agreement"].median() - v_pre["mean_agreement"].median()
            ),
            "n_videos_pre": int(len(v_pre)),
            "n_videos_post": int(len(v_post)),
        },
        "video_level_mean_of_means_AB": {
            "pre_2025": float(v_pre["mean_agreement"].mean()),
            "post_2025": float(v_post["mean_agreement"].mean()),
            "delta_post_minus_pre": float(
                v_post["mean_agreement"].mean() - v_pre["mean_agreement"].mean()
            ),
        },
    }
    (OUT / "effect_size_period.json").write_text(
        json.dumps(effect, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- Per-video scores with dates ---
    vscores.to_csv(OUT / "video_agreement_scores.csv", index=False)

    # Lowest-scoring videos post-2025
    low_post = (
        v_post.sort_values("mean_agreement")
        .head(30)[
            [
                "video_id",
                "title",
                "upload_date",
                "year",
                "n_syllables",
                "mean_agreement",
                "speech_s",
            ]
        ]
    )
    low_post.to_csv(OUT / "lowest_videos_2025plus.csv", index=False)

    # Highest-scoring videos post-2025 for contrast
    high_post = (
        v_post.sort_values("mean_agreement", ascending=False)
        .head(15)[
            [
                "video_id",
                "title",
                "upload_date",
                "year",
                "n_syllables",
                "mean_agreement",
                "speech_s",
            ]
        ]
    )
    high_post.to_csv(OUT / "highest_videos_2025plus.csv", index=False)

    # Cinema / archival keyword heuristic (as PIPELINE mentions)
    cinema_kw = (
        "李龍基|王青霞|任劍輝|白雪仙|新馬師曾|芳艷芬|紅線女|粵語長片|戲曲|電影|"
        "銀幕|影星|粵劇|唐滌生|林鳳|夏夢|于素秋|張活游|吳楚帆|白燕|紫羅蓮|"
        "中世紀|五六十|六十年代|七十年代|懷舊|經典金曲|主題曲|插曲|翻唱|合唱"
    )
    vscores["cinema_kw"] = (
        vscores["title"].fillna("").str.contains(cinema_kw, regex=True, case=False)
    )
    cinema_rows = []
    for period in ["pre-2025", "2025+"]:
        for flag, g in vscores[vscores["period"] == period].groupby("cinema_kw"):
            g2 = g[g["n_syllables"] > 0]
            if len(g2) == 0:
                continue
            # syllable-weighted from syl_ab
            vids = set(g2["video_id"])
            sg = syl_ab[syl_ab["video_id"].isin(vids)]
            cinema_rows.append(
                {
                    "period": period,
                    "cinema_kw": bool(flag),
                    "n_videos": int(len(g2)),
                    "n_syllables": int(len(sg)),
                    "mean_agreement_syl": agreement_rate(sg["jp_match"]),
                    "median_agreement_video": float(g2["mean_agreement"].median()),
                }
            )
    cinema_df = pd.DataFrame(cinema_rows)
    cinema_df.to_csv(OUT / "cinema_keyword_split.csv", index=False)

    # --- Other quality issues ---
    issues = {}
    issues["missing_upload_date_videos"] = int(videos["upload_dt"].isna().sum())
    issues["null_jp_match_syllables"] = int(syllables["jp_match"].isna().sum())
    issues["empty_jp_realized"] = int(
        (syllables["jp_realized"].isna() | (syllables["jp_realized"] == "")).sum()
    )
    issues["tier_C_windows"] = int((windows["tier"] == "C").sum())
    issues["tier_C_share_windows"] = float((windows["tier"] == "C").mean())
    issues["lang_not_yue"] = (
        windows["lang"].value_counts(dropna=False).head(20).to_dict()
    )
    issues["flag_sing_windows"] = int(windows["flag_sing"].fillna(0).sum())
    issues["flag_boiler_windows"] = int(windows["flag_boiler"].fillna(0).sum())
    issues["flag_simp_windows"] = int(windows["flag_simp"].fillna(0).sum())
    issues["tone_shift_suspect_windows"] = int(
        windows["tone_shift_suspect"].fillna(0).sum()
    )
    issues["coverage_lt_0_2"] = int((windows["coverage"].fillna(1) < 0.2).sum())
    issues["coverage_lt_0_5"] = int((windows["coverage"].fillna(1) < 0.5).sum())
    issues["dur_anomalies_windows_lt_1_5"] = int((windows["dur"] < 1.5).sum())
    issues["dur_anomalies_windows_gt_40"] = int((windows["dur"] > 40).sum())
    issues["zero_width_syllables"] = int((syllables["dur"].fillna(0) <= 0).sum())
    issues["zero_width_share"] = float((syllables["dur"].fillna(0) <= 0).mean())
    issues["verification_status"] = (
        syllables["verification_status"].value_counts(dropna=False).to_dict()
    )

    # Tier imbalance by period
    tier_period = (
        win.groupby(["period", "tier"]).size().unstack(fill_value=0)
    )
    tier_period.to_csv(OUT / "tier_by_period.csv")

    # Verdict mix by year (AB)
    verdict_year = (
        syl_ab.groupby(["year", "jp_match"]).size().unstack(fill_value=0)
    )
    verdict_year_share = verdict_year.div(verdict_year.sum(axis=1), axis=0)
    verdict_year.to_csv(OUT / "verdict_counts_by_year_AB.csv")
    verdict_year_share.to_csv(OUT / "verdict_share_by_year_AB.csv")

    # Window-level mean agreement by year (using syllable join)
    win_agree = (
        syl_ab.groupby("uid")
        .agg(
            mean_agreement=("jp_match", lambda x: float(x.isin(EXACT).mean())),
            n=("jp_match", "size"),
            video_id=("video_id", "first"),
            year=("year", "first"),
            period=("period", "first"),
            tier=("tier", "first"),
        )
        .reset_index()
    )
    win_agree.to_csv(OUT / "window_agreement_AB.csv", index=False)

    # Chars/sec and coverage by period
    win_ab = win[win["tier"].isin(["A", "B"])]
    qc_period = (
        win_ab.groupby("period")
        .agg(
            n=("uid", "size"),
            mean_cps=("chars_per_sec", "mean"),
            median_cps=("chars_per_sec", "median"),
            mean_coverage=("coverage", "mean"),
            median_coverage=("coverage", "median"),
            mean_dur=("dur", "mean"),
            sing_rate=("flag_sing", "mean"),
            boiler_rate=("flag_boiler", "mean"),
            simp_rate=("flag_simp", "mean"),
            tone_shift_rate=("tone_shift_suspect", "mean"),
        )
        .reset_index()
    )
    qc_period.to_csv(OUT / "window_qc_by_period_AB.csv", index=False)

    issues["window_qc_by_period_AB"] = qc_period.to_dict(orient="records")
    (OUT / "quality_issues.json").write_text(
        json.dumps(issues, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # --- Plots ---
    ab_year = by_year[by_year["scope"] == "AB"].dropna(subset=["year"])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(ab_year["year"].astype(int).astype(str), ab_year["mean_agreement"], color="#4C78A8")
    ax.set_ylim(0.6, 1.0)
    ax.set_ylabel("Agreement (exact_default + exact_alt)")
    ax.set_xlabel("Upload year")
    ax.set_title("Syllable agreement by video upload year (tiers A+B)")
    for _, r in ab_year.iterrows():
        ax.text(
            str(int(r["year"])),
            r["mean_agreement"] + 0.01,
            f"{r['mean_agreement']:.3f}\nn={int(r['n_syllables'])}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(OUT / "agreement_by_year_AB.png", dpi=150)
    plt.close(fig)

    # Video-level box/violin by year
    fig, ax = plt.subplots(figsize=(8, 4.5))
    years = sorted(vscores["year"].dropna().unique())
    data = [
        vscores[(vscores["year"] == y) & (vscores["n_syllables"] > 0)]["mean_agreement"].values
        for y in years
    ]
    ax.boxplot(data, tick_labels=[str(int(y)) for y in years], showfliers=True)
    ax.set_ylabel("Per-video mean agreement")
    ax.set_xlabel("Upload year")
    ax.set_title("Video-level agreement distribution by year (tiers A+B)")
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    fig.savefig(OUT / "video_agreement_boxplot_by_year.png", dpi=150)
    plt.close(fig)

    # Period histogram
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(
        v_pre["mean_agreement"],
        bins=30,
        alpha=0.6,
        label=f"pre-2025 (n={len(v_pre)})",
        color="#4C78A8",
    )
    ax.hist(
        v_post["mean_agreement"],
        bins=30,
        alpha=0.6,
        label=f"2025+ (n={len(v_post)})",
        color="#F58518",
    )
    ax.axvline(v_pre["mean_agreement"].median(), color="#4C78A8", linestyle="--", lw=1.5)
    ax.axvline(v_post["mean_agreement"].median(), color="#F58518", linestyle="--", lw=1.5)
    ax.set_xlabel("Per-video mean agreement")
    ax.set_ylabel("Videos")
    ax.set_title("Video agreement: pre-2025 vs 2025+")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "video_agreement_hist_period.png", dpi=150)
    plt.close(fig)

    # Print summary for stdout
    print("=== AGREEMENT BY YEAR (AB) ===")
    print(ab_year[["year", "n_videos", "n_windows", "n_syllables", "mean_agreement"]].to_string(index=False))
    print("\n=== BY PERIOD (AB) ===")
    print(by_period[by_period["scope"] == "AB"].to_string(index=False))
    print("\n=== EFFECT ===")
    print(json.dumps(effect, indent=2))
    print("\n=== CINEMA KW ===")
    print(cinema_df.to_string(index=False))
    print("\nWrote outputs to", OUT)


if __name__ == "__main__":
    main()
