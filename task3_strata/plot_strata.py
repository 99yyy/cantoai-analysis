#!/usr/bin/env python3
"""Plot Task3 film vs contemporary strata figures from existing CSVs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Prefer SC CJK so Chinese titles/labels render; fall back silently.
from matplotlib import font_manager

_CJK_CANDIDATES = [
    "Noto Sans CJK SC",
    "Noto Serif CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "SimHei",
]
_available = {f.name for f in font_manager.fontManager.ttflist}
_cjk = next((n for n in _CJK_CANDIDATES if n in _available), None)
_font_list = ([_cjk, "DejaVu Sans"] if _cjk else ["DejaVu Sans"])

plt.rcParams.update(
    {
        "font.sans-serif": _font_list,
        "font.family": "sans-serif",
        "axes.unicode_minus": False,
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "figure.dpi": 140,
        "savefig.dpi": 140,
        "savefig.bbox": "tight",
    }
)

FILM_COLOR = "#c44e52"
CONT_COLOR = "#4c72b0"
SNR_ORDER = ["<5", "5-10", "10-15", "15-20", ">20"]
SING_ORDER = ["<0.2", "0.2-0.5", ">0.5"]


def _err_from_ci(mean: float, lo: float, hi: float) -> tuple[float, float]:
    return max(0.0, mean - lo), max(0.0, hi - mean)


def plot_overall(summary: pd.DataFrame, out: Path) -> None:
    film = summary.loc[summary["contrast"] == "film_overall"].iloc[0]
    cont = summary.loc[summary["contrast"] == "contemporary_overall"].iloc[0]

    metrics = [
        ("agree_syl", "agree_syl_ci_low", "agree_syl_ci_high", "音节加权一致率"),
        (
            "agree_video_median",
            "agree_video_median_ci_low",
            "agree_video_median_ci_high",
            "视频中位一致率",
        ),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2), sharey=False)
    x = np.arange(2)
    width = 0.36

    for ax, (col, lo_c, hi_c, title) in zip(axes, metrics):
        f_m, c_m = float(film[col]), float(cont[col])
        f_err = _err_from_ci(f_m, float(film[lo_c]), float(film[hi_c]))
        c_err = _err_from_ci(c_m, float(cont[lo_c]), float(cont[hi_c]))
        bars_f = ax.bar(
            x[0],
            f_m,
            width,
            yerr=np.array(f_err).reshape(2, 1),
            color=FILM_COLOR,
            label="film",
            capsize=4,
            error_kw={"elinewidth": 1.2},
        )
        bars_c = ax.bar(
            x[1],
            c_m,
            width,
            yerr=np.array(c_err).reshape(2, 1),
            color=CONT_COLOR,
            label="contemporary",
            capsize=4,
            error_kw={"elinewidth": 1.2},
        )
        ax.set_xticks(x)
        ax.set_xticklabels(["film", "contemporary"])
        ax.set_ylabel("agreement")
        ax.set_title(title)
        ax.set_ylim(0.6, 1.0)
        ax.axhline(0, color="none")
        delta = f_m - c_m
        ax.text(
            0.5,
            0.02,
            f"Δ = {delta*100:.2f} pp",
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=10,
        )
        for bar, val in ((bars_f[0], f_m), (bars_c[0], c_m)):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                val + 0.012,
                f"{val*100:.1f}%",
                ha="center",
                va="bottom",
                fontsize=9,
            )
        ax.legend(loc="lower right", frameon=False)

    fig.suptitle("film vs contemporary 总体一致率（95% bootstrap CI）", y=1.02)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def _grouped_bins(
    df: pd.DataFrame,
    order: list[str],
    out: Path,
    title: str,
    xlabel: str,
    ylim: tuple[float, float] = (0.0, 1.0),
) -> None:
    film = df[df["subset"] == "film"].set_index("bin").loc[order]
    cont = df[df["subset"] == "contemporary"].set_index("bin").loc[order]

    x = np.arange(len(order))
    width = 0.38
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))

    for ax, col, lo_c, hi_c, ylab in (
        (
            axes[0],
            "agree_syl",
            "agree_syl_ci_low",
            "agree_syl_ci_high",
            "音节加权一致率",
        ),
        (
            axes[1],
            "agree_video_median",
            "agree_video_median_ci_low",
            "agree_video_median_ci_high",
            "视频中位一致率",
        ),
    ):
        f_m = film[col].to_numpy(dtype=float)
        c_m = cont[col].to_numpy(dtype=float)
        f_lo = film[lo_c].to_numpy(dtype=float)
        f_hi = film[hi_c].to_numpy(dtype=float)
        c_lo = cont[lo_c].to_numpy(dtype=float)
        c_hi = cont[hi_c].to_numpy(dtype=float)
        f_err = np.vstack([f_m - f_lo, f_hi - f_m])
        c_err = np.vstack([c_m - c_lo, c_hi - c_m])
        f_err = np.clip(f_err, 0, None)
        c_err = np.clip(c_err, 0, None)

        ax.bar(
            x - width / 2,
            f_m,
            width,
            yerr=f_err,
            color=FILM_COLOR,
            label="film",
            capsize=3,
            error_kw={"elinewidth": 1.0},
        )
        ax.bar(
            x + width / 2,
            c_m,
            width,
            yerr=c_err,
            color=CONT_COLOR,
            label="contemporary",
            capsize=3,
            error_kw={"elinewidth": 1.0},
        )
        ax.set_xticks(x)
        ax.set_xticklabels(order)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylab)
        ax.set_ylim(*ylim)
        ax.legend(frameon=False, loc="best")

    fig.suptitle(title, y=1.02)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_highsnr_onset(summary: pd.DataFrame, out: Path) -> None:
    film = summary.loc[summary["contrast"] == "film_dialogue_highsnr_n_ng_gw"].iloc[0]
    cont = summary.loc[summary["contrast"] == "contemporary_highsnr_n_ng_gw"].iloc[0]

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))
    x = np.arange(2)
    width = 0.4

    for ax, col, lo_c, hi_c, title in (
        (
            axes[0],
            "agree_syl",
            "agree_syl_ci_low",
            "agree_syl_ci_high",
            "音节加权一致率",
        ),
        (
            axes[1],
            "agree_video_median",
            "agree_video_median_ci_low",
            "agree_video_median_ci_high",
            "视频中位一致率",
        ),
    ):
        f_m, c_m = float(film[col]), float(cont[col])
        f_err = _err_from_ci(f_m, float(film[lo_c]), float(film[hi_c]))
        c_err = _err_from_ci(c_m, float(cont[lo_c]), float(cont[hi_c]))
        ax.bar(
            x[0],
            f_m,
            width,
            yerr=np.array(f_err).reshape(2, 1),
            color=FILM_COLOR,
            label="film",
            capsize=4,
        )
        ax.bar(
            x[1],
            c_m,
            width,
            yerr=np.array(c_err).reshape(2, 1),
            color=CONT_COLOR,
            label="contemporary",
            capsize=4,
        )
        ax.set_xticks(x)
        ax.set_xticklabels(["film", "contemporary"])
        ax.set_ylabel("agreement")
        ax.set_title(title)
        ax.set_ylim(0.0, 1.05)
        delta = f_m - c_m
        ax.text(
            0.5,
            0.02,
            f"Δ = {delta*100:.1f} pp\n"
            f"n_syl={int(film['n_syllables'])} vs {int(cont['n_syllables'])}",
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=9,
        )
        ax.legend(loc="lower right", frameon=False)

    fig.suptitle(
        "高 SNR 口白 n-/ng-/gw-（snr_db>15 且 singing_prob<0.2）",
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory with CSVs; figures written here",
    )
    args = ap.parse_args()
    d = args.dir

    summary = pd.read_csv(d / "summary_contrast.csv")
    snr = pd.read_csv(d / "agreement_by_snr.csv")
    singing = pd.read_csv(d / "agreement_by_singing.csv")

    out_overall = d / "fig_overall_film_vs_contemporary.png"
    out_snr = d / "fig_agreement_by_snr.png"
    out_sing = d / "fig_agreement_by_singing.png"
    out_onset = d / "fig_highsnr_dialogue_n_ng_gw.png"

    plot_overall(summary, out_overall)
    _grouped_bins(
        snr,
        SNR_ORDER,
        out_snr,
        "SNR 分箱：film vs contemporary（95% CI）",
        "SNR bin (dB)",
        ylim=(0.35, 1.0),
    )
    _grouped_bins(
        singing,
        SING_ORDER,
        out_sing,
        "singing_prob 分箱：film vs contemporary（95% CI）",
        "singing_prob bin",
        ylim=(0.0, 1.0),
    )
    plot_highsnr_onset(summary, out_onset)

    for p in (out_overall, out_snr, out_sing, out_onset):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
