"""TASK-9 worker: replay window-proxy SQL, row accounting, period-cluster bootstrap."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.bootstrap import (  # noqa: E402
    assert_bootstrap_B,
    assert_inconclusive_when_unreliable,
    conclusion_for_ci,
    make_stratum_seeds,
)
from src.frame import (  # noqa: E402
    assert_published_count,
    assert_syllables_count,
    assert_videos_count,
    assert_windows_count,
)
from src.groups import period_masks  # noqa: E402
from src.hashing import verify_corpus_hash  # noqa: E402
from src.pins import load_frame_counts  # noqa: E402
from src.status_io import sha256_file, write_json_atomic, write_status, write_text_atomic  # noqa: E402
from src.tables import load_table, open_corpus  # noqa: E402
from src.write_results import eval_derived, run_sql_file  # noqa: E402

SQL_NAMES = [
    "n_videos_pre",
    "n_videos_post",
    "n_unassigned_period",
    "n_windows_pre",
    "n_windows_post",
    "n_flag_sing_pre",
    "n_flag_sing_post",
    "rate_coverage_pre_pm",
    "rate_coverage_post_pm",
    "rate_coverage_median_pre_pm",
    "rate_coverage_median_post_pm",
    "gap_flag_sing_vidmed_pm",
    "gap_coverage_vidmed_pm",
    "gap_flag_sing_trim10_pm",
    "gap_coverage_trim10_pm",
]

DERIVED_ORDER = [
    ("rate_flag_sing_pre_pm", "1000 * (n_flag_sing_pre / n_windows_pre)"),
    ("rate_flag_sing_post_pm", "1000 * (n_flag_sing_post / n_windows_post)"),
    ("gap_flag_sing_pm", "rate_flag_sing_post_pm - rate_flag_sing_pre_pm"),
    ("gap_coverage_pm", "rate_coverage_post_pm - rate_coverage_pre_pm"),
]

ORDER = [
    "n_videos_pre",
    "n_videos_post",
    "n_unassigned_period",
    "n_windows_pre",
    "n_windows_post",
    "n_flag_sing_pre",
    "n_flag_sing_post",
    "rate_flag_sing_pre_pm",
    "rate_flag_sing_post_pm",
    "gap_flag_sing_pm",
    "rate_coverage_pre_pm",
    "rate_coverage_post_pm",
    "gap_coverage_pm",
    "rate_coverage_median_pre_pm",
    "rate_coverage_median_post_pm",
    "gap_flag_sing_vidmed_pm",
    "gap_coverage_vidmed_pm",
    "gap_flag_sing_trim10_pm",
    "gap_coverage_trim10_pm",
]

PERIOD_STRATA = ("pre", "post")
MASTER_SEED = 20260920
B = 2000
FLAG_OK = (0, 1)


def git_sha(repo_ROOT: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo_ROOT, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def table_columns(conn, table: str) -> list[str]:
    rows = conn.execute("pragma table_info(" + table + ")").fetchall()
    return [str(r[1]) for r in rows]


def json_num(name: str, value: float) -> int | float:
    if name.startswith("n_"):
        return int(round(value))
    return float(value)


def query_for(name: str) -> str:
    for derived_name, expr in DERIVED_ORDER:
        if derived_name == name:
            return "derived:" + expr
    return f"tasks/TASK-9/sql/{name}.sql"


def n_for(name: str, got: dict[str, float], videos_n: int) -> int:
    if name in {
        "n_videos_pre",
        "n_videos_post",
        "n_unassigned_period",
        "gap_flag_sing_vidmed_pm",
        "gap_coverage_vidmed_pm",
    }:
        return videos_n
    n_pre = int(got["n_windows_pre"])
    n_post = int(got["n_windows_post"])
    if name in {
        "n_windows_pre",
        "n_flag_sing_pre",
        "rate_flag_sing_pre_pm",
        "rate_coverage_pre_pm",
        "rate_coverage_median_pre_pm",
    }:
        return n_pre
    if name in {
        "n_windows_post",
        "n_flag_sing_post",
        "rate_flag_sing_post_pm",
        "rate_coverage_post_pm",
        "rate_coverage_median_post_pm",
    }:
        return n_post
    if name in {
        "gap_flag_sing_pm",
        "gap_coverage_pm",
        "gap_flag_sing_trim10_pm",
        "gap_coverage_trim10_pm",
    }:
        return n_pre + n_post
    raise ValueError("TASK-9: n_for received an undeclared number name")


def assert_counts_equal(label: str, sql_n: float, frame_n: int) -> None:
    if int(round(sql_n)) != int(frame_n):
        print(int(round(sql_n)), int(frame_n), label)
        raise ValueError("TASK-9: SQL count does not match the loaded frame")


def assert_close(label: str, sql_v: float, other_v: float) -> None:
    if not math.isfinite(sql_v) or not math.isfinite(other_v):
        print(sql_v, other_v, label)
        raise ValueError("TASK-9: a cross-check value is not finite")
    if abs(float(sql_v) - float(other_v)) > 1e-9:
        print(sql_v, other_v, label)
        raise ValueError("TASK-9: SQL value does not match the pandas cross-check")


def period_label(pre: pd.Series, post: pd.Series) -> pd.Series:
    if bool((pre & post).any()):
        raise ValueError("TASK-9: a row matched both pre and post")
    out = pd.Series("unassigned_period", index=pre.index)
    out.loc[pre] = "pre"
    out.loc[post] = "post"
    return out


def attach_video_fields(windows: pd.DataFrame, videos: pd.DataFrame) -> pd.DataFrame:
    for col in ("upload_date", "title", "period"):
        if col in windows.columns:
            raise ValueError("TASK-9: duplicate column when attaching video fields")
    upload_by_vid = dict(zip(videos["video_id"].tolist(), videos["upload_date"].tolist()))
    title_by_vid = dict(zip(videos["video_id"].tolist(), videos["title"].tolist()))
    out = windows.copy()
    vids = out["video_id"].tolist()
    missing = 0
    uploads: list[object] = []
    titles: list[object] = []
    for vid in vids:
        if vid not in upload_by_vid:
            missing += 1
            uploads.append(None)
            titles.append(None)
        else:
            uploads.append(upload_by_vid[vid])
            titles.append(title_by_vid[vid])
    if missing != 0:
        print(missing)
        raise ValueError("TASK-9: window video_id is missing from videos")
    out["upload_date"] = uploads
    out["title"] = titles
    return out


def median_pairs(pairs: list[tuple[float, str]]) -> float:
    n = len(pairs)
    if n == 0:
        raise ValueError("TASK-9: median of an empty set")
    ordered = sorted(pairs, key=lambda row: (row[0], row[1]))
    if n % 2 == 1:
        return float(ordered[(n + 1) // 2 - 1][0])
    left = float(ordered[n // 2 - 1][0])
    right = float(ordered[n // 2][0])
    return (left + right) / 2.0


def trim_k(G: int) -> tuple[int, int]:
    if G < 2:
        return 0, 1
    if 2 <= G < 20:
        return 1, 0
    return int(0.05 * G), 0


def drop_extreme(pool: pd.DataFrame, score_col: str, k: int) -> set[str]:
    ordered = pool.sort_values(
        [score_col, "title", "video_id"],
        ascending=True,
        kind="mergesort",
    )
    ids = ordered["video_id"].tolist()
    if k == 0:
        return set()
    dropped = set(ids[:k]) | set(ids[-k:])
    return dropped


def bh_adjusted(p_raw: dict[str, float], m: int) -> dict[str, float]:
    names = sorted(p_raw)
    if len(names) != m:
        raise ValueError("TASK-9: BH m does not equal the number of declared comparisons")
    order = sorted(names, key=lambda nm: p_raw[nm])
    adj: dict[str, float] = {}
    running = 1.0
    for rank, nm in enumerate(reversed(order), start=0):
        k = m - rank
        running = min(running, p_raw[nm] * m / k)
        adj[nm] = min(1.0, running)
    return {nm: adj[nm] for nm in names}


def two_sided_p(boot: np.ndarray, observed: float) -> float:
    if observed >= 0:
        tail = float(np.mean(boot <= 0.0))
    else:
        tail = float(np.mean(boot >= 0.0))
    return min(1.0, 2.0 * tail)


def q2_triggers(a: float, b: float, c: float) -> dict:
    vals = [a, b, c]
    labels = ("window", "vidmed", "trim10")
    pairs: list[dict] = []
    triggered = 0
    for i in range(3):
        for j in range(i + 1, 3):
            x, y = vals[i], vals[j]
            zero_vs_nonzero = (x == 0.0 and y != 0.0) or (y == 0.0 and x != 0.0)
            sign_mismatch = (x > 0.0 and y < 0.0) or (x < 0.0 and y > 0.0)
            ratio = None
            ratio_gt_2 = False
            if x != 0.0 and y != 0.0:
                ratio = max(abs(x), abs(y)) / min(abs(x), abs(y))
                ratio_gt_2 = bool(ratio > 2.0)
            hit = bool(zero_vs_nonzero or sign_mismatch or ratio_gt_2)
            if hit:
                triggered = 1
            pairs.append(
                {
                    "a": labels[i],
                    "b": labels[j],
                    "zero_vs_nonzero": int(zero_vs_nonzero),
                    "sign_mismatch": int(sign_mismatch),
                    "abs_ratio": ratio,
                    "ratio_gt_2": int(ratio_gt_2),
                    "triggered": int(hit),
                }
            )
    return {"triggered": triggered, "pairs": pairs}


def video_period_matrix(
    videos: pd.DataFrame,
    published: pd.DataFrame,
    period: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ids = videos.loc[videos["period"] == period, "video_id"].tolist()
    g = len(ids)
    nw = np.zeros(g, dtype=np.float64)
    ns = np.zeros(g, dtype=np.float64)
    sc = np.zeros(g, dtype=np.float64)
    idx = {vid: i for i, vid in enumerate(ids)}
    sub = published.loc[published["period"] == period]
    for vid, n in sub.groupby("video_id").size().items():
        nw[idx[vid]] = float(n)
    sing = sub.loc[sub["flag_sing"].eq(1)]
    for vid, n in sing.groupby("video_id").size().items():
        ns[idx[vid]] = float(n)
    for vid, total in sub.groupby("video_id")["coverage"].sum().items():
        sc[idx[vid]] = float(total)
    return nw, ns, sc


def bootstrap_gaps(
    videos: pd.DataFrame,
    published: pd.DataFrame,
    observed: dict[str, float],
) -> dict:
    assert_bootstrap_B(B)
    seeds = make_stratum_seeds(MASTER_SEED, PERIOD_STRATA)
    mats: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    g_h: dict[str, int] = {}
    for h in PERIOD_STRATA:
        mats[h] = video_period_matrix(videos, published, h)
        g_h[h] = int(mats[h][0].shape[0])
    pre_f = post_f = pre_c = post_c = None
    for h in PERIOD_STRATA:
        rng = np.random.default_rng(seeds[h])
        nw, ns, sc = mats[h]
        g = int(nw.shape[0])
        draws = rng.integers(0, g, size=(B, g))
        n = nw[draws].sum(axis=1)
        if bool((n <= 0).any()):
            raise ValueError("TASK-9: a bootstrap replicate had no published windows")
        s = ns[draws].sum(axis=1)
        c = sc[draws].sum(axis=1)
        rate_f = 1000.0 * s / n
        rate_c = 1000.0 * c / n
        if h == "pre":
            pre_f, pre_c = rate_f, rate_c
        else:
            post_f, post_c = rate_f, rate_c
    if pre_f is None or post_f is None or pre_c is None or post_c is None:
        raise ValueError("TASK-9: bootstrap missing a period stratum")
    boot = {
        "gap_flag_sing_pm": post_f - pre_f,
        "gap_coverage_pm": post_c - pre_c,
    }
    ci_unreliable_flags = {h: int(g_h[h] < 10) for h in PERIOD_STRATA}
    ci_unreliable = int(any(ci_unreliable_flags.values()))
    conclusion = conclusion_for_ci(ci_unreliable_flags, g_h)
    assert_inconclusive_when_unreliable(ci_unreliable, conclusion)
    p_raw: dict[str, float] = {}
    classes: dict[str, dict] = {}
    for name in ("gap_flag_sing_pm", "gap_coverage_pm"):
        samples = boot[name]
        lo, hi = np.quantile(samples, [0.025, 0.975])
        p_raw[name] = two_sided_p(samples, float(observed[name]))
        classes[name] = {
            "observed_pm": float(observed[name]),
            "ci95": [float(lo), float(hi)],
            "includes_0": bool(lo <= 0.0 <= hi),
        }
    p_bh = bh_adjusted(p_raw, 2)
    n_published_videos = {
        h: int(published.loc[published["period"] == h, "video_id"].nunique())
        for h in PERIOD_STRATA
    }
    for name in classes:
        row = classes[name]
        row["p_raw"] = p_raw[name]
        row["p_BH"] = p_bh[name]
        row["conclusion"] = conclusion
        if conclusion == "inconclusive":
            row["judgeable_videos"] = n_published_videos
    return {
        "B": B,
        "master_seed": MASTER_SEED,
        "stratum_seeds": {h: int(seeds[h]) for h in PERIOD_STRATA},
        "G_h": g_h,
        "ci_unreliable": ci_unreliable,
        "ci_unreliable_stratum": ci_unreliable_flags,
        "m": 2,
        "n_videos_with_published_windows": n_published_videos,
        "gaps": classes,
    }


def window_rates(df: pd.DataFrame) -> dict[str, float]:
    n = int(len(df))
    if n == 0:
        raise ValueError("TASK-9: a period has no published windows")
    n_flag = int(df["flag_sing"].eq(1).sum())
    mean_cov = float(df["coverage"].mean())
    return {
        "n_windows": float(n),
        "n_flag_sing": float(n_flag),
        "rate_flag_sing_pm": 1000.0 * n_flag / n,
        "rate_coverage_pm": 1000.0 * mean_cov,
    }


def open_analysis_text(
    got: dict[str, float],
    year_cells: list[dict],
    vidmed: dict,
    trim: dict,
    boot: dict,
    q2_flag: dict,
    q2_cov: dict,
    dropped_tier: dict,
    videos_n: int,
    descriptive: dict,
) -> str:
    flag_pre = got["rate_flag_sing_pre_pm"]
    flag_post = got["rate_flag_sing_post_pm"]
    flag_gap = got["gap_flag_sing_pm"]
    cov_pre = got["rate_coverage_pre_pm"]
    cov_post = got["rate_coverage_post_pm"]
    cov_gap = got["gap_coverage_pm"]
    flag_vid = got["gap_flag_sing_vidmed_pm"]
    cov_vid = got["gap_coverage_vidmed_pm"]
    flag_tr = got["gap_flag_sing_trim10_pm"]
    cov_tr = got["gap_coverage_trim10_pm"]
    boot_flag = boot["gaps"]["gap_flag_sing_pm"]
    boot_cov = boot["gaps"]["gap_coverage_pm"]
    q2_flag_txt = (
        "Q2 2x/sign rule triggered for flag_sing; this row is not an overall change."
        if q2_flag["triggered"]
        else (
            "Q2 2x/sign rule did not trigger for flag_sing "
            "(all three point values are 0)."
            if flag_gap == 0.0 and flag_vid == 0.0 and flag_tr == 0.0
            else "Q2 2x/sign rule did not trigger for flag_sing."
        )
    )
    q2_cov_txt = (
        "Q2 2x/sign rule triggered for coverage; this row is not an overall change."
        if q2_cov["triggered"]
        else "Q2 2x/sign rule did not trigger for coverage."
    )
    if boot["ci_unreliable"]:
        cov_vs0 = (
            "coverage cluster CI is marked ci_unreliable=1; "
            "conclusion=inconclusive for the window-weighted coverage gap"
        )
    elif boot_cov["includes_0"]:
        cov_vs0 = "coverage window-weighted 95% cluster interval includes 0"
    else:
        cov_vs0 = "coverage window-weighted 95% cluster interval excludes 0"
    if flag_post > flag_pre:
        sing_clause = "post flag_sing per-mille is higher than pre on published windows"
    else:
        sing_clause = (
            "post flag_sing per-mille is not higher than pre on published windows"
        )
    lines = [
        "# TASK-9 open analysis",
        "",
        f"Population: the {videos_n} videos of this channel. Declared numbers",
        "are published-window proxies (windows.tier IN ('A','B')), not",
        "judgeable-syllable agreement, and not jp_match class shares.",
        "",
        "## Window-weighted rates (declared)",
        "",
        f"- rate_flag_sing_pre_pm={flag_pre:.8f} (n_flag_sing_pre="
        f"{int(got['n_flag_sing_pre'])} / n_windows_pre={int(got['n_windows_pre'])})",
        f"- rate_flag_sing_post_pm={flag_post:.8f} (n_flag_sing_post="
        f"{int(got['n_flag_sing_post'])} / n_windows_post={int(got['n_windows_post'])})",
        f"- gap_flag_sing_pm={flag_gap:.8f} = rate_flag_sing_post_pm - rate_flag_sing_pre_pm",
        f"- rate_coverage_pre_pm={cov_pre:.8f}",
        f"- rate_coverage_post_pm={cov_post:.8f}",
        f"- gap_coverage_pm={cov_gap:.8f} = rate_coverage_post_pm - rate_coverage_pre_pm",
        "",
        "These two gaps are not definitionally equal to any closed task's",
        "total gap (TASK-6 gap_contract_pp, TASK-7 gap_other_common_pp, or",
        "TASK-8 share gaps). The window-weighted formula is each proxy's",
        "own post − pre. vidmed / trim10 reweight or subsample the same",
        "gap; they are not extra decomposition terms.",
        "",
        "coverage is not a proportion and this task does not define a higher",
        "or lower coverage mean as better or worse.",
        "",
        "## Tier filter (contract 23 / 27)",
        "",
        f"- windows dropped by windows.tier not in A+B: "
        f"{dropped_tier['n_windows_dropped']}",
        f"- among dropped windows, flag_sing=1: "
        f"{dropped_tier['n_flag_sing_dropped']}",
        f"- published A+B windows: {dropped_tier['n_windows_published']}",
        f"- published A+B windows with flag_sing=1: "
        f"{dropped_tier['n_flag_sing_published']}",
        "",
        "The tier rule already removes every flag_sing=1 window in this",
        "corpus. A published-set flag_sing rate of 0 is not the same as",
        "the channel having no singing-flag windows.",
        "",
        "## Year cells (inquiry Q1; descriptive=1)",
        "",
        "Natural unit of upload_date is calendar year substr(upload_date,1,4).",
        "2021 and 2023 are small cells and are not a trend.",
        "",
    ]
    for cell in year_cells:
        if cell.get("n_windows", 0) == 0:
            lines.append(
                f"- {cell['year']}: n_videos={cell['n_videos']}, "
                f"n_windows={cell['n_windows']} (no published-window rates; "
                f"descriptive=1)"
            )
        else:
            lines.append(
                f"- {cell['year']}: n_videos={cell['n_videos']}, "
                f"n_windows={cell['n_windows']}, "
                f"rate_flag_sing_pm={cell['rate_flag_sing_pm']:.8f}, "
                f"rate_coverage_pm={cell['rate_coverage_pm']:.8f} "
                f"(descriptive=1)"
            )
    lines.extend(
        [
            "",
            "## Q2 three-column table: flag_sing",
            "",
            f"- gap_flag_sing_pm={flag_gap:.8f}",
            f"- gap_flag_sing_vidmed_pm={flag_vid:.8f}",
            f"- gap_flag_sing_trim10_pm={flag_tr:.8f}",
            "",
            "Period rates used to recompute:",
            f"- window-weighted rate_flag_sing_pre_pm={flag_pre:.8f}, "
            f"rate_flag_sing_post_pm={flag_post:.8f}",
            f"- vidmed rate_flag_sing_pre_vidmed_pm="
            f"{vidmed['rate_flag_sing_pre_vidmed_pm']:.8f}, "
            f"rate_flag_sing_post_vidmed_pm="
            f"{vidmed['rate_flag_sing_post_vidmed_pm']:.8f} "
            f"(n_videos_pre={vidmed['n_videos_pre']}, "
            f"n_videos_post={vidmed['n_videos_post']}; not declared numbers)",
            f"- trim10 window-weighted rate_flag_sing_pre_pm="
            f"{trim['flag']['rate_flag_sing_pre_pm']:.8f}, "
            f"rate_flag_sing_post_pm={trim['flag']['rate_flag_sing_post_pm']:.8f} "
            f"(remaining n_windows_pre={int(trim['flag']['n_windows_pre'])}, "
            f"n_windows_post={int(trim['flag']['n_windows_post'])})",
            "",
            q2_flag_txt,
            "",
            "## Q2 three-column table: coverage",
            "",
            f"- gap_coverage_pm={cov_gap:.8f}",
            f"- gap_coverage_vidmed_pm={cov_vid:.8f}",
            f"- gap_coverage_trim10_pm={cov_tr:.8f}",
            "",
            "Period rates used to recompute:",
            f"- window-weighted rate_coverage_pre_pm={cov_pre:.8f}, "
            f"rate_coverage_post_pm={cov_post:.8f}",
            f"- vidmed rate_coverage_pre_vidmed_pm="
            f"{vidmed['rate_coverage_pre_vidmed_pm']:.8f}, "
            f"rate_coverage_post_vidmed_pm="
            f"{vidmed['rate_coverage_post_vidmed_pm']:.8f}",
            f"- trim10 window-weighted rate_coverage_pre_pm="
            f"{trim['coverage']['rate_coverage_pre_pm']:.8f}, "
            f"rate_coverage_post_pm={trim['coverage']['rate_coverage_post_pm']:.8f} "
            f"(remaining n_windows_pre={int(trim['coverage']['n_windows_pre'])}, "
            f"n_windows_post={int(trim['coverage']['n_windows_post'])})",
            "",
            q2_cov_txt,
            "If any two of window / vidmed / trim10 differ in sign or have",
            "absolute-value ratio > 2 (including one 0 and one non-0), the",
            "conclusion may not be written as an overall change.",
            "",
            "Window median coverage (descriptive=1, no p-value, no median gap",
            "declared):",
            f"- rate_coverage_median_pre_pm={got['rate_coverage_median_pre_pm']:.8f}",
            f"- rate_coverage_median_post_pm={got['rate_coverage_median_post_pm']:.8f}",
            "",
            "## Bias direction (inquiry Q5)",
            "",
            "flag_sing is a model flag proxy, not a content judgement and not",
            "a title-keyword class. 把非唱窗标成唱，会把 gap_flag_sing_pm 往正",
            "（迎合假说）推；把唱窗漏标，会往负推。",
            "",
            "## Cluster bootstrap (window-weighted gaps only; m=2)",
            "",
            f"B={boot['B']} whole-video_id resamples within period strata.",
            f"Master seed {boot['master_seed']}. Per-stratum seeds are",
            'int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16).',
            "",
            f"- pre: G_h={boot['G_h']['pre']}, videos with published A+B windows="
            f"{boot['n_videos_with_published_windows']['pre']}, "
            f"ci_unreliable stratum={boot['ci_unreliable_stratum']['pre']}",
            f"- post: G_h={boot['G_h']['post']}, videos with published A+B windows="
            f"{boot['n_videos_with_published_windows']['post']}, "
            f"ci_unreliable stratum={boot['ci_unreliable_stratum']['post']}",
            f"- any-stratum ci_unreliable={boot['ci_unreliable']}",
            f"- m={boot['m']}",
            "",
            (
                f"- gap_flag_sing_pm: 95% percentile CI "
                f"[{boot_flag['ci95'][0]:.6f}, {boot_flag['ci95'][1]:.6f}] pm; "
                f"includes 0={boot_flag['includes_0']}; "
                f"p_raw={boot_flag['p_raw']:.6g}; p_BH={boot_flag['p_BH']:.6g}; "
                f"conclusion={boot_flag['conclusion']}"
            ),
            (
                f"- gap_coverage_pm: 95% percentile CI "
                f"[{boot_cov['ci95'][0]:.6f}, {boot_cov['ci95'][1]:.6f}] pm; "
                f"includes 0={boot_cov['includes_0']}; "
                f"p_raw={boot_cov['p_raw']:.6g}; p_BH={boot_cov['p_BH']:.6g}; "
                f"conclusion={boot_cov['conclusion']}"
            ),
            "",
            "vidmed and trim10 are descriptive=1 for inference: they are not",
            "in m and do not carry p-values.",
            "",
            "## Optional descriptive=1 (not declared)",
            "",
            f"- chars_per_sec mean pre={descriptive['chars_per_sec_pre']:.8f}, "
            f"post={descriptive['chars_per_sec_post']:.8f}",
            f"- videos.speech_s / n_windows mean pre="
            f"{descriptive['speech_per_window_pre']:.8f}, "
            f"post={descriptive['speech_per_window_post']:.8f}",
            f"- window dur mean pre={descriptive['dur_pre']:.8f}, "
            f"post={descriptive['dur_post']:.8f}",
            f"- boundary_start shares on published windows: "
            f"{descriptive['boundary_start']}",
            f"- boundary_end shares on published windows: "
            f"{descriptive['boundary_end']}",
            "- aligned=1 on every window in this corpus; it separates nothing.",
            "",
            "## Conclusion",
            "",
            (
                f"On the {videos_n} videos of this channel, published A+B windows "
                f"do not carry a higher flag_sing per-mille after 2024 "
                f"(gap_flag_sing_pm={flag_gap:.4f}; window/vidmed/trim10 all 0; "
                f"{dropped_tier['n_flag_sing_dropped']} flag_sing=1 windows were "
                f"already removed by the A+B tier whitelist). Coverage mean "
                f"moved by gap_coverage_pm={cov_gap:.4f} pm (post lower; "
                f"{cov_vs0}; Q2 window={cov_gap:.4f}, vidmed={cov_vid:.4f}, "
                f"trim10={cov_tr:.4f}). {sing_clause}. Coverage is unsigned as "
                f"quality in this brief, so the coverage mean shift is not a "
                f"claim that post windows are worse."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def compute(
    corpus_PATH: str, readme_PATH: str, brief_PATH: str, sql_DIR: str, repo_ROOT: str
) -> dict:
    corpus_sha = verify_corpus_hash(corpus_PATH, readme_PATH)
    counts = load_frame_counts(brief_PATH, readme_PATH)
    conn = open_corpus(corpus_PATH)
    try:
        videos = load_table(conn, "videos")
        windows = load_table(conn, "windows")
        syllables = load_table(conn, "syllables")
        assert_videos_count(len(videos), counts.videos_expected, counts.videos_expected_tol)
        assert_windows_count(
            len(windows), counts.windows_expected, counts.windows_expected_tol
        )
        assert_syllables_count(
            len(syllables), counts.syllables_expected, counts.syllables_expected_tol
        )
        n_pub_syl = int(syllables["tier"].isin(("A", "B")).sum())
        assert_published_count(
            n_pub_syl, counts.published_expected, counts.published_expected_tol
        )
        inputs = {
            "data/corpus_v2.sqlite": {
                "sha256": corpus_sha,
                "tables": {
                    "videos": {
                        "rows": int(len(videos)),
                        "columns": table_columns(conn, "videos"),
                    },
                    "windows": {
                        "rows": int(len(windows)),
                        "columns": table_columns(conn, "windows"),
                    },
                    "syllables": {
                        "rows": int(len(syllables)),
                        "columns": table_columns(conn, "syllables"),
                    },
                },
            }
        }
        got: dict[str, float] = {}
        for name in SQL_NAMES:
            sql_FILE = str(Path(sql_DIR) / (name + ".sql"))
            text = Path(sql_FILE).read_text(encoding="utf-8")
            conn.execute("explain " + text)
            got[name] = run_sql_file(conn, sql_FILE)
        for name, expr in DERIVED_ORDER:
            got[name] = eval_derived(expr, got)
    finally:
        conn.close()

    steps = [
        {
            "step": "load_videos",
            "rule": "videos full table",
            "group": "all",
            "rows_before": int(len(videos)),
            "rows_after": int(len(videos)),
        },
        {
            "step": "load_windows",
            "rule": "windows full table",
            "group": "all",
            "rows_before": int(len(windows)),
            "rows_after": int(len(windows)),
        },
        {
            "step": "load_syllables",
            "rule": "syllables full table",
            "group": "all",
            "rows_before": int(len(syllables)),
            "rows_after": int(len(syllables)),
        },
        {
            "step": "tier_whitelist_syllables",
            "rule": "syllables.tier IN ('A','B')",
            "group": "all",
            "rows_before": int(len(syllables)),
            "rows_after": n_pub_syl,
        },
    ]

    if "period" in videos.columns:
        raise ValueError("TASK-9: duplicate column period on videos")
    v_pre, v_post, v_unassigned = period_masks(videos["upload_date"])
    videos = videos.copy()
    videos["period"] = period_label(v_pre, v_post)
    windows = attach_video_fields(windows, videos)
    w_pre, w_post, w_unassigned = period_masks(windows["upload_date"])
    windows["period"] = period_label(w_pre, w_post)

    assert_counts_equal("n_videos_pre", got["n_videos_pre"], int(v_pre.sum()))
    assert_counts_equal("n_videos_post", got["n_videos_post"], int(v_post.sum()))
    assert_counts_equal(
        "n_unassigned_period", got["n_unassigned_period"], int(v_unassigned.sum())
    )

    steps.append(
        {
            "step": "period_videos",
            "rule": "four-digit year <=2024 vs >=2025; neither predicate is unassigned",
            "group": "all",
            "rows_before": int(len(videos)),
            "rows_after": int(len(videos)),
            "n_pre": int(v_pre.sum()),
            "n_post": int(v_post.sum()),
            "n_unassigned": int(v_unassigned.sum()),
        }
    )

    is_ab = windows["tier"].isin(("A", "B"))
    n_dropped = int((~is_ab).sum())
    n_dropped_sing = int((~is_ab & windows["flag_sing"].eq(1)).sum())
    published = windows.loc[is_ab].copy()
    n_pub_win = int(len(published))
    n_pub_sing = int(published["flag_sing"].eq(1).sum())
    steps.append(
        {
            "step": "tier_whitelist_windows",
            "rule": "windows.tier IN ('A','B')",
            "group": "all",
            "rows_before": int(len(windows)),
            "rows_after": n_pub_win,
            "n_flag_sing_dropped": n_dropped_sing,
        }
    )

    flag_ok = published["flag_sing"].isin(FLAG_OK) & published["flag_sing"].notna()
    if bool((~flag_ok).any()):
        print(int((~flag_ok).sum()))
        raise ValueError("TASK-9: flag_sing on a published window is not 0 or 1")
    if bool(published["coverage"].isna().any()):
        print(int(published["coverage"].isna().sum()))
        raise ValueError("TASK-9: coverage is NULL on a published window")

    pub_pre = published.loc[published["period"] == "pre"]
    pub_post = published.loc[published["period"] == "post"]
    if int(len(pub_pre)) == 0 or int(len(pub_post)) == 0:
        print(int(len(pub_pre)), int(len(pub_post)))
        raise ValueError("TASK-9: a period has no published windows")

    steps.append(
        {
            "step": "period_published_windows",
            "rule": "same period predicates on published A+B windows",
            "group": "all",
            "rows_before": n_pub_win,
            "rows_after": n_pub_win,
            "n_pre": int(len(pub_pre)),
            "n_post": int(len(pub_post)),
            "n_unassigned": int((published["period"] == "unassigned_period").sum()),
        }
    )

    pre_rates = window_rates(pub_pre)
    post_rates = window_rates(pub_post)
    assert_counts_equal("n_windows_pre", got["n_windows_pre"], int(pre_rates["n_windows"]))
    assert_counts_equal("n_windows_post", got["n_windows_post"], int(post_rates["n_windows"]))
    assert_counts_equal(
        "n_flag_sing_pre", got["n_flag_sing_pre"], int(pre_rates["n_flag_sing"])
    )
    assert_counts_equal(
        "n_flag_sing_post", got["n_flag_sing_post"], int(post_rates["n_flag_sing"])
    )
    assert_close("rate_coverage_pre_pm", got["rate_coverage_pre_pm"], pre_rates["rate_coverage_pm"])
    assert_close(
        "rate_coverage_post_pm", got["rate_coverage_post_pm"], post_rates["rate_coverage_pm"]
    )
    assert_close(
        "rate_flag_sing_pre_pm",
        got["rate_flag_sing_pre_pm"],
        pre_rates["rate_flag_sing_pm"],
    )
    assert_close(
        "rate_flag_sing_post_pm",
        got["rate_flag_sing_post_pm"],
        post_rates["rate_flag_sing_pm"],
    )

    pre_med_pairs = list(zip(pub_pre["coverage"].tolist(), pub_pre["uid"].tolist()))
    post_med_pairs = list(zip(pub_post["coverage"].tolist(), pub_post["uid"].tolist()))
    assert_close(
        "rate_coverage_median_pre_pm",
        got["rate_coverage_median_pre_pm"],
        1000.0 * median_pairs(pre_med_pairs),
    )
    assert_close(
        "rate_coverage_median_post_pm",
        got["rate_coverage_median_post_pm"],
        1000.0 * median_pairs(post_med_pairs),
    )

    def vidmed_period(df: pd.DataFrame) -> dict[str, float]:
        if int(df["video_id"].nunique()) == 0:
            raise ValueError("TASK-9: vidmed period has no videos with published windows")
        rows = []
        for vid, grp in df.groupby("video_id", sort=False):
            n = int(len(grp))
            n_flag = int(grp["flag_sing"].eq(1).sum())
            mean_cov = float(grp["coverage"].mean())
            rows.append(
                {
                    "video_id": str(vid),
                    "rate_flag_sing_pm": 1000.0 * n_flag / n,
                    "mean_coverage": mean_cov,
                }
            )
        flag_med = median_pairs([(r["rate_flag_sing_pm"], r["video_id"]) for r in rows])
        cov_med = median_pairs([(r["mean_coverage"], r["video_id"]) for r in rows])
        return {
            "n_videos": float(len(rows)),
            "rate_flag_sing_vidmed_pm": flag_med,
            "rate_coverage_vidmed_pm": 1000.0 * cov_med,
        }

    vid_pre = vidmed_period(pub_pre)
    vid_post = vidmed_period(pub_post)
    assert_close(
        "gap_flag_sing_vidmed_pm",
        got["gap_flag_sing_vidmed_pm"],
        vid_post["rate_flag_sing_vidmed_pm"] - vid_pre["rate_flag_sing_vidmed_pm"],
    )
    assert_close(
        "gap_coverage_vidmed_pm",
        got["gap_coverage_vidmed_pm"],
        vid_post["rate_coverage_vidmed_pm"] - vid_pre["rate_coverage_vidmed_pm"],
    )
    steps.append(
        {
            "step": "vidmed_clusters",
            "rule": "videos with >=1 published window in that period",
            "group": "all",
            "rows_before": int(len(videos)),
            "rows_after": int(vid_pre["n_videos"] + vid_post["n_videos"]),
            "n_pre": int(vid_pre["n_videos"]),
            "n_post": int(vid_post["n_videos"]),
        }
    )

    pool_pub = published.loc[published["period"].isin(("pre", "post"))].copy()
    pool_rows = []
    for vid, grp in pool_pub.groupby("video_id", sort=False):
        n = int(len(grp))
        n_flag = int(grp["flag_sing"].eq(1).sum())
        mean_cov = float(grp["coverage"].mean())
        title = str(grp["title"].iloc[0])
        period = str(grp["period"].iloc[0])
        pool_rows.append(
            {
                "video_id": str(vid),
                "title": title,
                "period": period,
                "n_windows": n,
                "n_flag_sing": n_flag,
                "score_flag": 1000.0 * n_flag / n,
                "score_cov": mean_cov,
            }
        )
    pool = pd.DataFrame(pool_rows)
    G = int(len(pool))
    k, trim10_skipped = trim_k(G)
    steps.append(
        {
            "step": "trim10_pool",
            "rule": "video_id with >=1 published window in pre or post",
            "group": "all",
            "rows_before": int(len(videos)),
            "rows_after": G,
            "G": G,
            "k": k,
            "trim10_skipped": trim10_skipped,
        }
    )
    drop_flag = drop_extreme(pool, "score_flag", k)
    drop_cov = drop_extreme(pool, "score_cov", k)
    steps.append(
        {
            "step": "trim10_flag_sing_drop",
            "rule": "drop lowest k and highest k clusters by flag_sing score, title, video_id",
            "group": "flag_sing",
            "rows_before": G,
            "rows_after": G - len(drop_flag),
            "n_dropped_videos": len(drop_flag),
            "k": k,
        }
    )
    steps.append(
        {
            "step": "trim10_coverage_drop",
            "rule": "drop lowest k and highest k clusters by mean coverage, title, video_id",
            "group": "coverage",
            "rows_before": G,
            "rows_after": G - len(drop_cov),
            "n_dropped_videos": len(drop_cov),
            "k": k,
        }
    )

    def trim_rates(dropped: set[str]) -> dict[str, float]:
        kept = pool_pub.loc[~pool_pub["video_id"].isin(dropped)]
        pre = kept.loc[kept["period"] == "pre"]
        post = kept.loc[kept["period"] == "post"]
        if int(len(pre)) == 0 or int(len(post)) == 0:
            print(int(len(pre)), int(len(post)))
            raise ValueError("TASK-9: remaining trim10 period has no windows")
        bad_flag = ~pre["flag_sing"].isin(FLAG_OK) | pre["flag_sing"].isna()
        bad_flag = bad_flag | (~post["flag_sing"].isin(FLAG_OK) | post["flag_sing"].isna())
        if bool(bad_flag.any()):
            raise ValueError("TASK-9: flag_sing on a remaining trim10 window is not 0 or 1")
        if bool(pre["coverage"].isna().any()) or bool(post["coverage"].isna().any()):
            raise ValueError("TASK-9: coverage is NULL on a remaining trim10 window")
        pre_r = window_rates(pre)
        post_r = window_rates(post)
        return {
            "n_windows_pre": pre_r["n_windows"],
            "n_windows_post": post_r["n_windows"],
            "rate_flag_sing_pre_pm": pre_r["rate_flag_sing_pm"],
            "rate_flag_sing_post_pm": post_r["rate_flag_sing_pm"],
            "rate_coverage_pre_pm": pre_r["rate_coverage_pm"],
            "rate_coverage_post_pm": post_r["rate_coverage_pm"],
            "gap_flag_sing_pm": pre_r["rate_flag_sing_pm"] * 0.0
            + post_r["rate_flag_sing_pm"]
            - pre_r["rate_flag_sing_pm"],
            "gap_coverage_pm": post_r["rate_coverage_pm"] - pre_r["rate_coverage_pm"],
        }

    trim_flag = trim_rates(drop_flag)
    trim_cov = trim_rates(drop_cov)
    assert_close(
        "gap_flag_sing_trim10_pm",
        got["gap_flag_sing_trim10_pm"],
        trim_flag["gap_flag_sing_pm"],
    )
    assert_close(
        "gap_coverage_trim10_pm",
        got["gap_coverage_trim10_pm"],
        trim_cov["gap_coverage_pm"],
    )

    year_raw = videos["upload_date"].astype(str).str.slice(0, 4)
    four = year_raw.str.fullmatch(r"[0-9]{4}").fillna(False)
    pub_year = published["upload_date"].astype(str).str.slice(0, 4)
    year_cells: list[dict] = []
    years = sorted(year_raw.loc[four].unique().tolist())
    for y in years:
        v_n = int((year_raw == y).sum())
        cell_win = published.loc[pub_year == y]
        n_w = int(len(cell_win))
        cell = {"year": str(y), "n_videos": v_n, "n_windows": n_w, "descriptive": 1}
        if n_w == 0:
            year_cells.append(cell)
            continue
        n_flag = int(cell_win["flag_sing"].eq(1).sum())
        cell["rate_flag_sing_pm"] = 1000.0 * n_flag / n_w
        cell["rate_coverage_pm"] = 1000.0 * float(cell_win["coverage"].mean())
        year_cells.append(cell)
    n_un_year = int((~four).sum())
    un_win = published.loc[~pub_year.str.fullmatch(r"[0-9]{4}").fillna(False)]
    un_cell = {
        "year": "unassigned",
        "n_videos": n_un_year,
        "n_windows": int(len(un_win)),
        "descriptive": 1,
    }
    if int(len(un_win)) > 0:
        un_cell["rate_flag_sing_pm"] = 1000.0 * int(un_win["flag_sing"].eq(1).sum()) / int(
            len(un_win)
        )
        un_cell["rate_coverage_pm"] = 1000.0 * float(un_win["coverage"].mean())
    year_cells.append(un_cell)

    videos_n = int(counts.videos_expected)
    rows = []
    for name in ORDER:
        rows.append(
            {
                "name": name,
                "value": json_num(name, got[name]),
                "n": n_for(name, got, videos_n),
                "query": query_for(name),
            }
        )

    boot = bootstrap_gaps(
        videos,
        published,
        {
            "gap_flag_sing_pm": float(got["gap_flag_sing_pm"]),
            "gap_coverage_pm": float(got["gap_coverage_pm"]),
        },
    )
    q2_flag = q2_triggers(
        float(got["gap_flag_sing_pm"]),
        float(got["gap_flag_sing_vidmed_pm"]),
        float(got["gap_flag_sing_trim10_pm"]),
    )
    q2_cov = q2_triggers(
        float(got["gap_coverage_pm"]),
        float(got["gap_coverage_vidmed_pm"]),
        float(got["gap_coverage_trim10_pm"]),
    )

    v_pre_df = videos.loc[videos["period"] == "pre"]
    v_post_df = videos.loc[videos["period"] == "post"]
    descriptive = {
        "chars_per_sec_pre": float(pub_pre["chars_per_sec"].mean()),
        "chars_per_sec_post": float(pub_post["chars_per_sec"].mean()),
        "dur_pre": float(pub_pre["dur"].mean()),
        "dur_post": float(pub_post["dur"].mean()),
        "speech_per_window_pre": float(
            (v_pre_df["speech_s"] / v_pre_df["n_windows"]).mean()
        ),
        "speech_per_window_post": float(
            (v_post_df["speech_s"] / v_post_df["n_windows"]).mean()
        ),
        "boundary_start": {
            str(k): int(v) / n_pub_win
            for k, v in published["boundary_start"].value_counts(dropna=False).items()
        },
        "boundary_end": {
            str(k): int(v) / n_pub_win
            for k, v in published["boundary_end"].value_counts(dropna=False).items()
        },
    }

    vidmed_out = {
        "n_videos_pre": int(vid_pre["n_videos"]),
        "n_videos_post": int(vid_post["n_videos"]),
        "rate_flag_sing_pre_vidmed_pm": vid_pre["rate_flag_sing_vidmed_pm"],
        "rate_flag_sing_post_vidmed_pm": vid_post["rate_flag_sing_vidmed_pm"],
        "rate_coverage_pre_vidmed_pm": vid_pre["rate_coverage_vidmed_pm"],
        "rate_coverage_post_vidmed_pm": vid_post["rate_coverage_vidmed_pm"],
    }
    trim_out = {
        "G": G,
        "k": k,
        "trim10_skipped": trim10_skipped,
        "rule": (
            "k=0 if G<2; k=1 if 2<=G<20; else floor(0.05*G); "
            "drop lowest k and highest k by (score, title, video_id); "
            "flag_sing and coverage dropped sets are independent"
        ),
        "n_dropped_videos_flag_sing": len(drop_flag),
        "n_dropped_videos_coverage": len(drop_cov),
        "flag": trim_flag,
        "coverage": trim_cov,
    }
    dropped_tier = {
        "n_windows_dropped": n_dropped,
        "n_flag_sing_dropped": n_dropped_sing,
        "n_windows_published": n_pub_win,
        "n_flag_sing_published": n_pub_sing,
        "n_videos_without_published_windows": int(
            len(videos) - published["video_id"].nunique()
        ),
    }
    analysis = open_analysis_text(
        got,
        year_cells,
        vidmed_out,
        trim_out,
        boot,
        q2_flag,
        q2_cov,
        dropped_tier,
        videos_n,
        descriptive,
    )
    n_no_pub = int((~videos["video_id"].isin(set(published["video_id"].tolist()))).sum())
    steps.append(
        {
            "step": "videos_without_published_windows",
            "rule": "video has zero windows.tier IN ('A','B')",
            "group": "all",
            "rows_before": int(len(videos)),
            "rows_after": int(len(videos)) - n_no_pub,
            "n_removed": n_no_pub,
        }
    )
    manifest = {
        "git_sha": git_sha(repo_ROOT),
        "inputs": inputs,
        "frame": {
            "videos_expected": int(counts.videos_expected),
            "windows_expected": int(counts.windows_expected),
            "syllables_expected": int(counts.syllables_expected),
            "published_expected": int(counts.published_expected),
        },
        "steps": steps,
        "year_cells": year_cells,
        "vidmed": vidmed_out,
        "trim10": {
            "G": G,
            "k": k,
            "trim10_skipped": trim10_skipped,
            "rule": trim_out["rule"],
            "n_dropped_videos_flag_sing": len(drop_flag),
            "n_dropped_videos_coverage": len(drop_cov),
            "flag_remaining_windows_pre": int(trim_flag["n_windows_pre"]),
            "flag_remaining_windows_post": int(trim_flag["n_windows_post"]),
            "coverage_remaining_windows_pre": int(trim_cov["n_windows_pre"]),
            "coverage_remaining_windows_post": int(trim_cov["n_windows_post"]),
            "flag_period_rates_pm": {
                "pre": trim_flag["rate_flag_sing_pre_pm"],
                "post": trim_flag["rate_flag_sing_post_pm"],
            },
            "coverage_period_rates_pm": {
                "pre": trim_cov["rate_coverage_pre_pm"],
                "post": trim_cov["rate_coverage_post_pm"],
            },
        },
        "tier_filter": dropped_tier,
        "q2": {"flag_sing": q2_flag, "coverage": q2_cov},
        "descriptive": 1,
        "descriptive_optional": descriptive,
        "window_weighted": {
            "rate_flag_sing_pre_pm": got["rate_flag_sing_pre_pm"],
            "rate_flag_sing_post_pm": got["rate_flag_sing_post_pm"],
            "gap_flag_sing_pm": got["gap_flag_sing_pm"],
            "rate_coverage_pre_pm": got["rate_coverage_pre_pm"],
            "rate_coverage_post_pm": got["rate_coverage_post_pm"],
            "gap_coverage_pm": got["gap_coverage_pm"],
        },
    }
    return {
        "rows": rows,
        "manifest": manifest,
        "bootstrap": boot,
        "analysis": analysis,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_PATH", required=True)
    parser.add_argument("--readme_PATH", required=True)
    parser.add_argument("--brief_PATH", required=True)
    parser.add_argument("--sql_DIR", required=True)
    parser.add_argument("--out_DIR", required=True)
    parser.add_argument("--repo_ROOT", required=True)
    args = parser.parse_args()
    out_DIR = Path(args.out_DIR)
    out_DIR.mkdir(parents=True, exist_ok=True)
    status_FILE = str(out_DIR / "STATUS.json")
    write_status(status_FILE, {"status": "running"})
    payload = compute(
        args.corpus_PATH,
        args.readme_PATH,
        args.brief_PATH,
        args.sql_DIR,
        args.repo_ROOT,
    )
    results_FILE = str(out_DIR / "results.json")
    manifest_FILE = str(out_DIR / "manifest.json")
    boot_FILE = str(out_DIR / "bootstrap.json")
    analysis_FILE = str(out_DIR / "open_analysis.md")
    write_json_atomic(results_FILE, payload["rows"])
    write_json_atomic(manifest_FILE, payload["manifest"])
    write_json_atomic(boot_FILE, payload["bootstrap"])
    write_text_atomic(analysis_FILE, payload["analysis"])
    write_status(
        status_FILE,
        {
            "status": "complete",
            "outputs": {
                "results.json": sha256_file(results_FILE),
                "manifest.json": sha256_file(manifest_FILE),
                "bootstrap.json": sha256_file(boot_FILE),
                "open_analysis.md": sha256_file(analysis_FILE),
            },
        },
    )


if __name__ == "__main__":
    main()
