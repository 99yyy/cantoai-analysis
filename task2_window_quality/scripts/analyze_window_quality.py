#!/usr/bin/env python3
"""从 window_quality_with_flags.csv 再生摘要、singing 对照表与三张图。

用法（在任务目录下）:
  .venv/bin/python scripts/analyze_window_quality.py
  .venv/bin/python scripts/analyze_window_quality.py --csv window_quality_with_flags.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "window_quality_with_flags.csv"
COLS = ["music_prob", "singing_prob", "snr_db", "dnsmos_ovrl"]


def load_df(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    need = {"window_id", "flag_sing", *COLS}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"CSV missing columns: {sorted(missing)}")
    if df[COLS].isna().any().any():
        raise SystemExit("NaNs in quality columns")
    return df


def write_summary(df: pd.DataFrame, out: Path) -> dict:
    stats = {
        "n": int(len(df)),
        "means": {c: float(df[c].mean()) for c in COLS},
        "medians": {c: float(df[c].median()) for c in COLS},
        "p25": {c: float(df[c].quantile(0.25)) for c in COLS},
        "p75": {c: float(df[c].quantile(0.75)) for c in COLS},
        "singing_prob_lt_0.2_share": float((df["singing_prob"] < 0.2).mean()),
        "flag_sing_n": int((df["flag_sing"] == 1).sum()),
        "flag_sing_singing_prob_mean": float(
            df.loc[df["flag_sing"] == 1, "singing_prob"].mean()
        ),
        "flag_sing_singing_prob_median": float(
            df.loc[df["flag_sing"] == 1, "singing_prob"].median()
        ),
        "flag_sing0_singing_prob_mean": float(
            df.loc[df["flag_sing"] == 0, "singing_prob"].mean()
        ),
        "flag_sing0_singing_prob_median": float(
            df.loc[df["flag_sing"] == 0, "singing_prob"].median()
        ),
        "unmarked_singing_prob_ge_0.5": int(
            ((df["flag_sing"] == 0) & (df["singing_prob"] >= 0.5)).sum()
        ),
        "marked_singing_prob_lt_0.2": int(
            ((df["flag_sing"] == 1) & (df["singing_prob"] < 0.2)).sum()
        ),
    }
    med0 = stats["flag_sing0_singing_prob_median"]
    med1 = stats["flag_sing_singing_prob_median"]
    stats["singing_prob_median_ratio_marked_over_unmarked"] = (
        float(med1 / med0) if med0 else None
    )
    out.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def write_singing_tables(df: pd.DataFrame, root: Path) -> None:
    rows = []
    for thr in [0.1, 0.2, 0.3, 0.5]:
        rows.append(
            {
                "threshold": thr,
                "unmarked_ge_thr": int(
                    ((df["flag_sing"] == 0) & (df["singing_prob"] >= thr)).sum()
                ),
                "marked_lt_thr": int(
                    ((df["flag_sing"] == 1) & (df["singing_prob"] < thr)).sum()
                ),
                "marked_n": int((df["flag_sing"] == 1).sum()),
                "unmarked_n": int((df["flag_sing"] == 0).sum()),
            }
        )
    pd.DataFrame(rows).to_csv(
        root / "singing_flag_contrast_by_threshold.csv", index=False
    )

    marked = df.loc[df["flag_sing"] == 1, ["window_id", *COLS]].sort_values(
        "singing_prob"
    )
    marked.to_csv(root / "singing_flag_marked_scores.csv", index=False)

    miss = (
        df.loc[(df["flag_sing"] == 0) & (df["singing_prob"] >= 0.5), ["window_id", *COLS]]
        .sort_values("singing_prob", ascending=False)
    )
    miss.to_csv(root / "singing_miss_suspect_unmarked_ge0.5.csv", index=False)


def write_plots(df: pd.DataFrame, root: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    for ax, col in zip(axes.ravel(), COLS):
        ax.hist(df[col], bins=50, color="#4C78A8", edgecolor="none")
        ax.set_title(col)
        ax.set_xlabel(col)
        ax.set_ylabel("count")
    fig.tight_layout()
    fig.savefig(root / "dist_histograms.png", dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    for ax, col in zip(axes.ravel(), COLS):
        ax.boxplot(df[col], vert=True, showfliers=False)
        ax.set_title(col)
        ax.set_ylabel(col)
    fig.tight_layout()
    fig.savefig(root / "dist_boxplots.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(
        df.loc[df["flag_sing"] == 0, "singing_prob"],
        bins=40,
        alpha=0.6,
        label=f"flag_sing=0 (n={(df.flag_sing==0).sum()})",
        color="#4C78A8",
    )
    ax.hist(
        df.loc[df["flag_sing"] == 1, "singing_prob"],
        bins=20,
        alpha=0.8,
        label=f"flag_sing=1 (n={(df.flag_sing==1).sum()})",
        color="#F58518",
    )
    ax.axvline(0.2, color="red", ls="--", label="thr 0.2")
    ax.set_xlabel("singing_prob")
    ax.set_ylabel("count")
    ax.legend()
    ax.set_title("singing_prob vs flag_sing")
    fig.tight_layout()
    fig.savefig(root / "singing_prob_vs_flag_sing.png", dpi=120)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args()
    root = args.root
    df = load_df(args.csv)
    stats = write_summary(df, root / "summary_stats.json")
    write_singing_tables(df, root)
    write_plots(df, root)
    print(json.dumps(stats, indent=2))
    print("Wrote summary_stats.json, singing_*.csv, three plots under", root)


if __name__ == "__main__":
    main()
