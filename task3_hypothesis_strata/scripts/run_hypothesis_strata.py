#!/usr/bin/env python3
"""
Stratified hypothesis analysis for iCantonese corpus.

This script performs stratified agreement analysis between film (電影口白) and 
contemporary-only content, computing syllable-weighted and video-median agreement
rates with bootstrap confidence intervals.

Usage:
    python run_hypothesis_strata.py --db fixtures/sample.sqlite \
        --quality fixtures/sample_window_quality.csv \
        --multilabel task3_multilabel_flags/video_multilabel_flags.csv \
        --out task3_hypothesis_strata/_sample_out \
        --seed 0 --bootstrap 200

For full data:
    python run_hypothesis_strata.py --db /path/to/corpus.sqlite \
        --quality task2_window_quality/window_quality.csv \
        --multilabel task3_multilabel_flags/video_multilabel_flags.csv \
        --out task3_hypothesis_strata/output \
        --seed 0 --bootstrap 2000
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================================
# Constants
# ============================================================================

# Agreement definition: jp_match in {exact_default, exact_alt} constitutes agreement
EXACT_MATCHES = {"exact_default", "exact_alt"}

# Default tier filter (A+B)
DEFAULT_TIERS = ["A", "B"]

# Film dialogue threshold: singing_prob < 0.2 for non-singing content
SINGING_THRESHOLD = 0.2

# SNR bins (dB)
SNR_BINS = [
    ("<5", lambda x: x < 5),
    ("5-10", lambda x: (x >= 5) & (x < 10)),
    ("10-15", lambda x: (x >= 10) & (x < 15)),
    ("15-20", lambda x: (x >= 15) & (x < 20)),
    (">20", lambda x: x >= 20),
]

# Singing probability bins
SINGING_BINS = [
    ("<0.2", lambda x: x < 0.2),
    ("0.2-0.5", lambda x: (x >= 0.2) & (x < 0.5)),
    (">0.5", lambda x: x >= 0.5),
]

# Speech rate bins (chars_per_sec) - based on typical Cantonese speech rates
RATE_BINS = [
    ("<3", lambda x: x < 3),
    ("3-5", lambda x: (x >= 3) & (x < 5)),
    ("5-7", lambda x: (x >= 5) & (x < 7)),
    (">7", lambda x: x >= 7),
]


# ============================================================================
# Jyutping parsing utilities
# ============================================================================

def parse_initial(jp: str | None) -> str:
    """
    Parse the initial consonant (声母) from a jyutping string.
    
    Categories:
    - n-: 泥母 (nasal n)
    - l-: 來母 (lateral l)
    - ng-: 疑母 (velar nasal)
    - zero: 零声母 (no initial, starts with vowel or glide j/w)
    - gw-/kw-: 合口見組 (labialized velars)
    - g-/k-: 見組 (velars without labialization)
    - other: all other initials (b, p, m, f, d, t, s, z, c, h, etc.)
    
    The classification follows standard Cantonese phonological categories,
    focusing on the initials most relevant to merger phenomena.
    """
    if not jp or not isinstance(jp, str):
        return "other"
    
    # Normalize: strip tone digit and convert to lowercase
    jp_clean = jp.lower().rstrip("0123456")
    
    if not jp_clean:
        return "other"
    
    # Order matters: check longer sequences first
    if jp_clean.startswith("ng"):
        return "ng-"
    if jp_clean.startswith("gw"):
        return "gw-/kw-"
    if jp_clean.startswith("kw"):
        return "gw-/kw-"
    if jp_clean.startswith("n"):
        return "n-"
    if jp_clean.startswith("l"):
        return "l-"
    if jp_clean.startswith("g"):
        return "g-/k-"
    if jp_clean.startswith("k"):
        return "g-/k-"
    
    # Zero initial: starts with vowel (a, e, i, o, u) or glide (j, w)
    # Note: 'j' in jyutping is a palatal glide [j], 'w' is labial glide [w]
    if jp_clean[0] in "aeiou":
        return "zero"
    if jp_clean.startswith("j") or jp_clean.startswith("w"):
        return "zero"
    
    return "other"


def parse_coda(jp: str | None) -> str:
    """
    Parse the coda (韵尾) from a jyutping string.
    
    Categories:
    - -n: 鼻韵尾 n
    - -ng: 鼻韵尾 ng
    - -t: 入声韵尾 t
    - -k: 入声韵尾 k
    - -p: 入声韵尾 p
    - -m: 鼻韵尾 m (less common)
    - open: 开音节 (no coda)
    
    The classification follows standard Cantonese phonological categories.
    """
    if not jp or not isinstance(jp, str):
        return "open"
    
    # Normalize: strip tone digit and convert to lowercase
    jp_clean = jp.lower().rstrip("0123456")
    
    if not jp_clean:
        return "open"
    
    # Order matters: check longer sequences first
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
    """
    Extract the tone number (1-6) from a jyutping string.
    Returns 0 if no valid tone is found.
    """
    if not jp or not isinstance(jp, str):
        return 0
    
    for c in jp[::-1]:  # Check from end
        if c.isdigit():
            tone = int(c)
            if 1 <= tone <= 6:
                return tone
    return 0


# ============================================================================
# Data loading
# ============================================================================

def load_data(
    db_path: Path,
    quality_path: Path,
    multilabel_path: Path,
    tiers: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and join all required data sources."""
    
    con = sqlite3.connect(db_path)
    videos = pd.read_sql_query("SELECT * FROM videos", con)
    windows = pd.read_sql_query("SELECT * FROM windows", con)
    syllables = pd.read_sql_query("SELECT * FROM syllables", con)
    con.close()
    
    quality = pd.read_csv(quality_path)
    multilabel = pd.read_csv(multilabel_path)
    
    # Filter by tier
    windows = windows[windows["tier"].isin(tiers)].copy()
    syllables = syllables[syllables["tier"].isin(tiers)].copy()
    
    # Join quality onto windows (window_id matches uid)
    windows = windows.merge(
        quality.rename(columns={"window_id": "uid"}),
        on="uid",
        how="left",
    )
    
    # Join video flags onto windows and syllables
    flag_cols = ["video_id", "film_flag", "contemporary_only"]
    windows = windows.merge(
        multilabel[flag_cols],
        on="video_id",
        how="left",
    )
    syllables = syllables.merge(
        multilabel[flag_cols],
        on="video_id",
        how="left",
    )
    
    # Join window-level quality/chars_per_sec onto syllables
    syl_join_cols = ["uid", "singing_prob", "snr_db", "chars_per_sec"]
    available_cols = [c for c in syl_join_cols if c in windows.columns]
    if available_cols:
        syllables = syllables.merge(
            windows[available_cols],
            on="uid",
            how="left",
        )
    
    return videos, windows, syllables, quality, multilabel


# ============================================================================
# Agreement computation
# ============================================================================

def is_agreement(jp_match: pd.Series) -> pd.Series:
    """Check if jp_match indicates agreement."""
    return jp_match.isin(EXACT_MATCHES)


def syllable_weighted_agreement(syl: pd.DataFrame) -> float:
    """Compute syllable-weighted agreement rate."""
    if len(syl) == 0:
        return np.nan
    return float(is_agreement(syl["jp_match"]).mean())


def video_median_agreement(syl: pd.DataFrame) -> float:
    """Compute median of per-video agreement rates."""
    if len(syl) == 0:
        return np.nan
    
    video_rates = (
        syl.groupby("video_id")["jp_match"]
        .apply(lambda x: float(is_agreement(x).mean()))
    )
    
    if len(video_rates) == 0:
        return np.nan
    
    return float(video_rates.median())


# ============================================================================
# Bootstrap confidence intervals
# ============================================================================

def bootstrap_ci(
    syl: pd.DataFrame,
    metric_fn,
    n_bootstrap: int,
    seed: int,
) -> tuple[float, float, float]:
    """
    Compute bootstrap confidence interval by resampling videos.
    
    Returns:
        (point_estimate, ci_low, ci_high)
    """
    point_est = metric_fn(syl)
    
    if len(syl) == 0 or pd.isna(point_est):
        return (np.nan, np.nan, np.nan)
    
    rng = np.random.default_rng(seed)
    video_ids = syl["video_id"].unique()
    n_videos = len(video_ids)
    
    if n_videos == 0:
        return (point_est, np.nan, np.nan)
    
    if n_videos == 1:
        # Can't resample with only one video
        return (point_est, point_est, point_est)
    
    boot_estimates = []
    for _ in range(n_bootstrap):
        # Resample videos with replacement
        sampled_vids = rng.choice(video_ids, size=n_videos, replace=True)
        # Get all syllables for sampled videos (may have duplicates)
        boot_syl = pd.concat([syl[syl["video_id"] == vid] for vid in sampled_vids], ignore_index=True)
        boot_est = metric_fn(boot_syl)
        if not pd.isna(boot_est):
            boot_estimates.append(boot_est)
    
    if len(boot_estimates) < 10:
        return (point_est, np.nan, np.nan)
    
    ci_low = float(np.percentile(boot_estimates, 2.5))
    ci_high = float(np.percentile(boot_estimates, 97.5))
    
    return (point_est, ci_low, ci_high)


# ============================================================================
# Stratification functions
# ============================================================================

def compute_stratum_stats(
    syl: pd.DataFrame,
    subset_name: str,
    bin_name: str,
    n_bootstrap: int,
    seed: int,
) -> dict:
    """Compute all statistics for a single stratum."""
    
    n_syllables = len(syl)
    n_videos = syl["video_id"].nunique() if n_syllables > 0 else 0
    
    syl_rate, syl_ci_low, syl_ci_high = bootstrap_ci(
        syl, syllable_weighted_agreement, n_bootstrap, seed
    )
    vid_rate, vid_ci_low, vid_ci_high = bootstrap_ci(
        syl, video_median_agreement, n_bootstrap, seed
    )
    
    return {
        "subset": subset_name,
        "bin": bin_name,
        "n_syllables": n_syllables,
        "n_videos": n_videos,
        "agree_syl": syl_rate,
        "agree_syl_ci_low": syl_ci_low,
        "agree_syl_ci_high": syl_ci_high,
        "agree_video_median": vid_rate,
        "agree_video_median_ci_low": vid_ci_low,
        "agree_video_median_ci_high": vid_ci_high,
    }


def stratify_by_axis(
    syl_film: pd.DataFrame,
    syl_contemp: pd.DataFrame,
    axis_name: str,
    bin_fn,  # function that returns (bin_name, mask) for each syllable
    n_bootstrap: int,
    seed: int,
) -> pd.DataFrame:
    """Stratify by a given axis and compute stats for both subsets."""
    
    rows = []
    
    for df, subset_name in [(syl_film, "film"), (syl_contemp, "contemporary")]:
        if len(df) == 0:
            continue
        
        bins = bin_fn(df)
        for bin_name, mask in bins:
            syl_bin = df[mask]
            if len(syl_bin) == 0:
                continue
            stats = compute_stratum_stats(syl_bin, subset_name, bin_name, n_bootstrap, seed)
            rows.append(stats)
    
    return pd.DataFrame(rows)


def get_onset_bins(syl: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Get bins for onset (initial) stratification."""
    syl = syl.copy()
    syl["_onset"] = syl["jp_default"].apply(parse_initial)
    
    categories = ["n-", "l-", "ng-", "zero", "gw-/kw-", "g-/k-", "other"]
    return [(cat, syl["_onset"] == cat) for cat in categories]


def get_coda_bins(syl: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Get bins for coda stratification."""
    syl = syl.copy()
    syl["_coda"] = syl["jp_default"].apply(parse_coda)
    
    categories = ["-n", "-ng", "-t", "-k", "-p", "-m", "open"]
    return [(cat, syl["_coda"] == cat) for cat in categories]


def get_tone_bins(syl: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Get bins for tone stratification (tones 1-6)."""
    syl = syl.copy()
    syl["_tone"] = syl["jp_default"].apply(parse_tone)
    
    return [(str(t), syl["_tone"] == t) for t in range(1, 7)]


def get_snr_bins(syl: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Get bins for SNR stratification."""
    return [(name, fn(syl["snr_db"])) for name, fn in SNR_BINS]


def get_singing_bins(syl: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Get bins for singing probability stratification."""
    return [(name, fn(syl["singing_prob"])) for name, fn in SINGING_BINS]


def get_rate_bins(syl: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Get bins for speech rate (chars_per_sec) stratification."""
    return [(name, fn(syl["chars_per_sec"])) for name, fn in RATE_BINS]


# ============================================================================
# Tone 1 confusion analysis
# ============================================================================

def analyze_tone1_confusion(
    syl: pd.DataFrame,
    subset_name: str,
    n_bootstrap: int,
    seed: int,
) -> dict:
    """
    Analyze tone 1 heard as tone 4 or 6.
    
    Uses jp_realized to check if dictionary tone 1 was perceived as tone 4 or 6.
    """
    syl = syl.copy()
    syl["_dict_tone"] = syl["jp_default"].apply(parse_tone)
    syl["_realized_tone"] = syl["jp_realized"].apply(parse_tone)
    
    tone1_syl = syl[syl["_dict_tone"] == 1]
    
    if len(tone1_syl) == 0:
        return {
            "subset": subset_name,
            "n_tone1_syllables": 0,
            "n_videos": 0,
            "heard_as_4_rate": np.nan,
            "heard_as_6_rate": np.nan,
            "heard_as_4_or_6_rate": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
        }
    
    heard_4 = (tone1_syl["_realized_tone"] == 4).mean()
    heard_6 = (tone1_syl["_realized_tone"] == 6).mean()
    heard_4_or_6 = ((tone1_syl["_realized_tone"] == 4) | (tone1_syl["_realized_tone"] == 6)).mean()
    
    # Bootstrap for combined rate
    def confusion_rate(df):
        df = df.copy()
        df["_dict_tone"] = df["jp_default"].apply(parse_tone)
        df["_realized_tone"] = df["jp_realized"].apply(parse_tone)
        t1 = df[df["_dict_tone"] == 1]
        if len(t1) == 0:
            return np.nan
        return float(((t1["_realized_tone"] == 4) | (t1["_realized_tone"] == 6)).mean())
    
    _, ci_low, ci_high = bootstrap_ci(syl, confusion_rate, n_bootstrap, seed)
    
    return {
        "subset": subset_name,
        "n_tone1_syllables": int(len(tone1_syl)),
        "n_videos": int(tone1_syl["video_id"].nunique()),
        "heard_as_4_rate": float(heard_4),
        "heard_as_6_rate": float(heard_6),
        "heard_as_4_or_6_rate": float(heard_4_or_6),
        "ci_low": float(ci_low) if not pd.isna(ci_low) else np.nan,
        "ci_high": float(ci_high) if not pd.isna(ci_high) else np.nan,
    }


# ============================================================================
# Summary contrast tables
# ============================================================================

def compute_summary_contrasts(
    syl_film: pd.DataFrame,
    syl_contemp: pd.DataFrame,
    windows_film: pd.DataFrame,
    n_bootstrap: int,
    seed: int,
) -> pd.DataFrame:
    """
    Compute summary contrast tables for hypothesis testing.
    
    1. Agreement recovery after removing singing_prob > 0.5 windows (film subset)
    2. High-SNR film dialogue vs contemporary comparison for n-/ng-/gw- initials
    3. Overall comparison for hypothesis A/B/C
    """
    rows = []
    
    # ========================================================================
    # 1. Film agreement with vs without high-singing windows
    # ========================================================================
    
    # Full film
    full_rate, full_ci_low, full_ci_high = bootstrap_ci(
        syl_film, syllable_weighted_agreement, n_bootstrap, seed
    )
    full_vid_rate, full_vid_ci_low, full_vid_ci_high = bootstrap_ci(
        syl_film, video_median_agreement, n_bootstrap, seed
    )
    
    rows.append({
        "contrast": "film_all",
        "description": "Film subset (all windows)",
        "n_syllables": len(syl_film),
        "n_videos": syl_film["video_id"].nunique() if len(syl_film) > 0 else 0,
        "agree_syl": full_rate,
        "agree_syl_ci_low": full_ci_low,
        "agree_syl_ci_high": full_ci_high,
        "agree_video_median": full_vid_rate,
        "agree_video_median_ci_low": full_vid_ci_low,
        "agree_video_median_ci_high": full_vid_ci_high,
    })
    
    # Film without high-singing (singing_prob <= 0.5)
    syl_film_no_sing = syl_film[syl_film["singing_prob"] <= 0.5]
    ns_rate, ns_ci_low, ns_ci_high = bootstrap_ci(
        syl_film_no_sing, syllable_weighted_agreement, n_bootstrap, seed
    )
    ns_vid_rate, ns_vid_ci_low, ns_vid_ci_high = bootstrap_ci(
        syl_film_no_sing, video_median_agreement, n_bootstrap, seed
    )
    
    rows.append({
        "contrast": "film_no_high_singing",
        "description": "Film subset (singing_prob <= 0.5)",
        "n_syllables": len(syl_film_no_sing),
        "n_videos": syl_film_no_sing["video_id"].nunique() if len(syl_film_no_sing) > 0 else 0,
        "agree_syl": ns_rate,
        "agree_syl_ci_low": ns_ci_low,
        "agree_syl_ci_high": ns_ci_high,
        "agree_video_median": ns_vid_rate,
        "agree_video_median_ci_low": ns_vid_ci_low,
        "agree_video_median_ci_high": ns_vid_ci_high,
    })
    
    # Delta
    rows.append({
        "contrast": "film_singing_removal_delta",
        "description": "Agreement recovery (delta) after removing singing_prob>0.5",
        "n_syllables": len(syl_film) - len(syl_film_no_sing),
        "n_videos": np.nan,
        "agree_syl": ns_rate - full_rate if not (pd.isna(ns_rate) or pd.isna(full_rate)) else np.nan,
        "agree_syl_ci_low": np.nan,
        "agree_syl_ci_high": np.nan,
        "agree_video_median": ns_vid_rate - full_vid_rate if not (pd.isna(ns_vid_rate) or pd.isna(full_vid_rate)) else np.nan,
        "agree_video_median_ci_low": np.nan,
        "agree_video_median_ci_high": np.nan,
    })
    
    # ========================================================================
    # 2. High-SNR film dialogue: n-/ng-/gw- comparison with contemporary
    # ========================================================================
    
    # Film dialogue = film_flag=1 AND singing_prob < 0.2
    # High SNR = snr_db > 15
    
    syl_film_dialogue = syl_film[syl_film["singing_prob"] < SINGING_THRESHOLD]
    syl_film_dialogue_highsnr = syl_film_dialogue[syl_film_dialogue["snr_db"] > 15]
    
    syl_contemp_highsnr = syl_contemp[syl_contemp["snr_db"] > 15]
    
    # Filter for n-/ng-/gw- initials
    target_initials = {"n-", "ng-", "gw-/kw-"}
    
    def filter_target_initials(df):
        if len(df) == 0:
            return df
        df = df.copy()
        df["_onset"] = df["jp_default"].apply(parse_initial)
        return df[df["_onset"].isin(target_initials)]
    
    film_target = filter_target_initials(syl_film_dialogue_highsnr)
    contemp_target = filter_target_initials(syl_contemp_highsnr)
    
    for name, df in [("film_dialogue_highsnr_n_ng_gw", film_target), 
                      ("contemporary_highsnr_n_ng_gw", contemp_target)]:
        rate, ci_low, ci_high = bootstrap_ci(df, syllable_weighted_agreement, n_bootstrap, seed)
        vid_rate, vid_ci_low, vid_ci_high = bootstrap_ci(df, video_median_agreement, n_bootstrap, seed)
        
        rows.append({
            "contrast": name,
            "description": f"{name.replace('_', ' ')} (snr_db>15, n-/ng-/gw- initials)",
            "n_syllables": len(df),
            "n_videos": df["video_id"].nunique() if len(df) > 0 else 0,
            "agree_syl": rate,
            "agree_syl_ci_low": ci_low,
            "agree_syl_ci_high": ci_high,
            "agree_video_median": vid_rate,
            "agree_video_median_ci_low": vid_ci_low,
            "agree_video_median_ci_high": vid_ci_high,
        })
    
    # ========================================================================
    # 3. Overall film vs contemporary comparison
    # ========================================================================
    
    for name, df in [("film_overall", syl_film), ("contemporary_overall", syl_contemp)]:
        rate, ci_low, ci_high = bootstrap_ci(df, syllable_weighted_agreement, n_bootstrap, seed)
        vid_rate, vid_ci_low, vid_ci_high = bootstrap_ci(df, video_median_agreement, n_bootstrap, seed)
        
        rows.append({
            "contrast": name,
            "description": f"{name.replace('_', ' ')} agreement",
            "n_syllables": len(df),
            "n_videos": df["video_id"].nunique() if len(df) > 0 else 0,
            "agree_syl": rate,
            "agree_syl_ci_low": ci_low,
            "agree_syl_ci_high": ci_high,
            "agree_video_median": vid_rate,
            "agree_video_median_ci_low": vid_ci_low,
            "agree_video_median_ci_high": vid_ci_high,
        })
    
    return pd.DataFrame(rows)


# ============================================================================
# Main entry point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Stratified hypothesis analysis for iCantonese corpus"
    )
    parser.add_argument(
        "--db", type=Path, required=True,
        help="Path to SQLite database"
    )
    parser.add_argument(
        "--quality", type=Path, required=True,
        help="Path to window_quality.csv"
    )
    parser.add_argument(
        "--multilabel", type=Path, required=True,
        help="Path to video_multilabel_flags.csv"
    )
    parser.add_argument(
        "--out", type=Path, required=True,
        help="Output directory"
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="Random seed for bootstrap (default: 0)"
    )
    parser.add_argument(
        "--bootstrap", type=int, default=2000,
        help="Number of bootstrap iterations (default: 2000)"
    )
    parser.add_argument(
        "--tiers", nargs="+", default=["A", "B"],
        help="Tiers to include (default: A B)"
    )
    
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading data from {args.db}...")
    videos, windows, syllables, quality, multilabel = load_data(
        args.db, args.quality, args.multilabel, args.tiers
    )
    
    print(f"  Videos: {len(videos)}")
    print(f"  Windows: {len(windows)}")
    print(f"  Syllables: {len(syllables)}")
    print(f"  Tiers: {args.tiers}")
    print(f"  Bootstrap: {args.bootstrap}")
    print(f"  Seed: {args.seed}")
    
    # ========================================================================
    # Subset definitions
    # ========================================================================
    
    # Film subset: film_flag = 1
    syl_film = syllables[syllables["film_flag"] == 1].copy()
    windows_film = windows[windows["film_flag"] == 1].copy()
    
    # Contemporary subset: contemporary_only = 1
    syl_contemp = syllables[syllables["contemporary_only"] == 1].copy()
    windows_contemp = windows[windows["contemporary_only"] == 1].copy()
    
    print(f"\nFilm subset: {len(syl_film)} syllables, {syl_film['video_id'].nunique()} videos")
    print(f"Contemporary subset: {len(syl_contemp)} syllables, {syl_contemp['video_id'].nunique()} videos")
    
    # ========================================================================
    # Stratified analyses
    # ========================================================================
    
    print("\nComputing stratified agreement rates...")
    
    # a. By onset (initial)
    print("  - By onset (initial)...")
    df_onset = stratify_by_axis(syl_film, syl_contemp, "onset", get_onset_bins, args.bootstrap, args.seed)
    df_onset.to_csv(args.out / "agreement_by_onset.csv", index=False)
    
    # b. By coda
    print("  - By coda...")
    df_coda = stratify_by_axis(syl_film, syl_contemp, "coda", get_coda_bins, args.bootstrap, args.seed)
    df_coda.to_csv(args.out / "agreement_by_coda.csv", index=False)
    
    # c. By tone
    print("  - By tone...")
    df_tone = stratify_by_axis(syl_film, syl_contemp, "tone", get_tone_bins, args.bootstrap, args.seed)
    df_tone.to_csv(args.out / "agreement_by_tone.csv", index=False)
    
    # d. By SNR
    print("  - By SNR...")
    df_snr = stratify_by_axis(syl_film, syl_contemp, "snr", get_snr_bins, args.bootstrap, args.seed)
    df_snr.to_csv(args.out / "agreement_by_snr.csv", index=False)
    
    # e. By singing probability
    print("  - By singing probability...")
    df_singing = stratify_by_axis(syl_film, syl_contemp, "singing", get_singing_bins, args.bootstrap, args.seed)
    df_singing.to_csv(args.out / "agreement_by_singing.csv", index=False)
    
    # f. By speech rate (chars_per_sec)
    print("  - By speech rate...")
    df_rate = stratify_by_axis(syl_film, syl_contemp, "rate", get_rate_bins, args.bootstrap, args.seed)
    df_rate.to_csv(args.out / "agreement_by_rate.csv", index=False)
    
    # ========================================================================
    # Tone 1 confusion analysis
    # ========================================================================
    
    print("  - Tone 1 confusion analysis...")
    tone1_rows = []
    tone1_rows.append(analyze_tone1_confusion(syl_film, "film", args.bootstrap, args.seed))
    tone1_rows.append(analyze_tone1_confusion(syl_contemp, "contemporary", args.bootstrap, args.seed))
    df_tone1 = pd.DataFrame(tone1_rows)
    df_tone1.to_csv(args.out / "tone1_confusion.csv", index=False)
    
    # ========================================================================
    # Summary contrasts
    # ========================================================================
    
    print("  - Summary contrasts...")
    df_summary = compute_summary_contrasts(syl_film, syl_contemp, windows_film, args.bootstrap, args.seed)
    df_summary.to_csv(args.out / "summary_contrast.csv", index=False)
    
    # ========================================================================
    # Print summary
    # ========================================================================
    
    print("\n" + "=" * 60)
    print("Output files written to:", args.out)
    print("=" * 60)
    
    print("\n--- Agreement by onset (first 10 rows) ---")
    print(df_onset.head(10).to_string(index=False))
    
    print("\n--- Summary contrasts ---")
    print(df_summary.to_string(index=False))
    
    print("\n--- Tone 1 confusion ---")
    print(df_tone1.to_string(index=False))
    
    # Validation checks
    print("\n" + "=" * 60)
    print("Validation checks:")
    print("=" * 60)
    
    n_videos_total = syllables["video_id"].nunique()
    has_film = (df_onset["subset"] == "film").any() if len(df_onset) > 0 else False
    has_contemp = (df_onset["subset"] == "contemporary").any() if len(df_onset) > 0 else False
    
    print(f"  Total videos (in syllables): {n_videos_total}")
    print(f"  Has film subset rows: {has_film}")
    print(f"  Has contemporary subset rows: {has_contemp}")
    
    # Check required output files exist
    required_files = [
        "agreement_by_onset.csv",
        "agreement_by_coda.csv",
        "agreement_by_tone.csv",
        "agreement_by_snr.csv",
        "agreement_by_singing.csv",
        "agreement_by_rate.csv",
        "summary_contrast.csv",
    ]
    
    all_exist = all((args.out / f).exists() for f in required_files)
    print(f"  All required output files exist: {all_exist}")
    
    print("\nDone!")
    return 0


if __name__ == "__main__":
    exit(main())
