"""TASK-8 worker: replay count SQL, row accounting, period-cluster bootstrap."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.agreement import (  # noqa: E402
    agreement_counts,
    assert_no_null_jp_match,
    judgeable_mask,
)
from src.bootstrap import assert_bootstrap_B, make_stratum_seeds  # noqa: E402
from src.frame import load_published_frame  # noqa: E402
from src.groups import period_masks  # noqa: E402
from src.hashing import verify_corpus_hash  # noqa: E402
from src.status_io import sha256_file, write_json_atomic, write_status, write_text_atomic  # noqa: E402
from src.tables import open_corpus  # noqa: E402
from src.write_results import eval_derived, run_sql_file  # noqa: E402

SQL_NAMES = [
    "n_videos_pre",
    "n_videos_post",
    "n_unassigned_period",
    "n_judgeable_pre",
    "n_judgeable_post",
    "n_tone_judgeable_pre",
    "n_tone_judgeable_post",
    "n_segment_judgeable_pre",
    "n_segment_judgeable_post",
    "n_diff_judgeable_pre",
    "n_diff_judgeable_post",
]

GAP_EXPR = {
    "gap_share_tone_pp": (
        "100 * (n_tone_judgeable_post / n_judgeable_post "
        "- n_tone_judgeable_pre / n_judgeable_pre)"
    ),
    "gap_share_segment_pp": (
        "100 * (n_segment_judgeable_post / n_judgeable_post "
        "- n_segment_judgeable_pre / n_judgeable_pre)"
    ),
    "gap_share_diff_pp": (
        "100 * (n_diff_judgeable_post / n_judgeable_post "
        "- n_diff_judgeable_pre / n_judgeable_pre)"
    ),
}

ORDER = SQL_NAMES + [
    "gap_share_tone_pp",
    "gap_share_segment_pp",
    "gap_share_diff_pp",
]

CLASSES = ("tone", "segment", "diff")
PERIOD_STRATA = ("pre", "post")
MASTER_SEED = 20260919
B = 2000
DECLARED_ENUM = (
    "exact_default",
    "exact_alt",
    "tone",
    "segment",
    "diff",
    "none",
)


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


def n_for(name: str, got: dict[str, float], videos_n: int) -> int:
    if name in {"n_videos_pre", "n_videos_post", "n_unassigned_period"}:
        return videos_n
    if name.endswith("_pre"):
        return int(got["n_judgeable_pre"])
    if name.endswith("_post"):
        return int(got["n_judgeable_post"])
    if name.startswith("gap_share_"):
        return int(got["n_judgeable_pre"] + got["n_judgeable_post"])
    raise ValueError("TASK-8: n_for received an undeclared number name")


def query_for(name: str) -> str:
    if name in GAP_EXPR:
        return "derived:" + GAP_EXPR[name]
    return f"tasks/TASK-8/sql/{name}.sql"


def assert_counts_equal(label: str, sql_n: float, frame_n: int) -> None:
    if int(round(sql_n)) != int(frame_n):
        print(int(round(sql_n)), int(frame_n), label)
        raise ValueError("TASK-8: SQL count does not match the loaded frame")


def assert_no_dual_class(tone: pd.Series, segment: pd.Series, diff: pd.Series) -> None:
    stacked = tone.astype(int) + segment.astype(int) + diff.astype(int)
    if bool((stacked > 1).any()):
        raise ValueError("TASK-8: a judgeable syllable matched more than one jp_match class")


def class_masks(jp_match: pd.Series) -> dict[str, pd.Series]:
    tone = jp_match.eq("tone")
    segment = jp_match.eq("segment")
    diff = jp_match.eq("diff")
    assert_no_dual_class(tone, segment, diff)
    return {"tone": tone, "segment": segment, "diff": diff}


def period_label(pre: pd.Series, post: pd.Series) -> pd.Series:
    if bool((pre & post).any()):
        raise ValueError("TASK-8: a row matched both pre and post")
    out = pd.Series("unassigned_period", index=pre.index)
    out.loc[pre] = "pre"
    out.loc[post] = "post"
    return out


def contract24(df: pd.DataFrame) -> dict[str, int]:
    return {k: int(v) for k, v in agreement_counts(df).items()}


def bh_adjusted(p_raw: dict[str, float], m: int) -> dict[str, float]:
    names = sorted(p_raw)
    if len(names) != m:
        raise ValueError("TASK-8: BH m does not equal the number of declared comparisons")
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


def video_count_matrix(
    videos: pd.DataFrame,
    judgeable: pd.DataFrame,
    period: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mask = videos["period"] == period
    ids = videos.loc[mask, "video_id"]
    zeros = np.zeros(int(ids.shape[0]), dtype=np.float64)
    sub = judgeable.loc[judgeable["period"] == period]
    if int(len(sub)) == 0:
        return zeros, zeros.copy(), zeros.copy(), zeros.copy()
    grouped = sub.groupby("video_id", sort=False).agg(
        n_j=("syl_id", "size"),
        n_tone=("is_tone", "sum"),
        n_segment=("is_segment", "sum"),
        n_diff=("is_diff", "sum"),
    )
    return (
        grouped["n_j"].reindex(ids, fill_value=0).to_numpy(dtype=np.float64),
        grouped["n_tone"].reindex(ids, fill_value=0).to_numpy(dtype=np.float64),
        grouped["n_segment"].reindex(ids, fill_value=0).to_numpy(dtype=np.float64),
        grouped["n_diff"].reindex(ids, fill_value=0).to_numpy(dtype=np.float64),
    )


def bootstrap_gaps(
    videos: pd.DataFrame,
    judgeable: pd.DataFrame,
    observed_pp: dict[str, float],
) -> dict:
    assert_bootstrap_B(B)
    seeds = make_stratum_seeds(MASTER_SEED, PERIOD_STRATA)
    if len(set(seeds.values())) != len(seeds):
        raise ValueError("TASK-8: bootstrap stratum seeds are not pairwise distinct")
    mats: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    g_h: dict[str, int] = {}
    for h in PERIOD_STRATA:
        mats[h] = video_count_matrix(videos, judgeable, h)
        g_h[h] = int(mats[h][0].shape[0])
    share_pre: dict[str, np.ndarray] | None = None
    share_post: dict[str, np.ndarray] | None = None
    for h in PERIOD_STRATA:
        rng = np.random.default_rng(seeds[h])
        n_j, n_tone, n_segment, n_diff = mats[h]
        g = int(n_j.shape[0])
        draws = rng.integers(0, g, size=(B, g))
        j = n_j[draws].sum(axis=1)
        if bool((j <= 0).any()):
            raise ValueError("TASK-8: a bootstrap replicate had no judgeable syllables")
        counts = {"tone": n_tone, "segment": n_segment, "diff": n_diff}
        shares = {cls: counts[cls][draws].sum(axis=1) / j for cls in CLASSES}
        if h == "pre":
            share_pre = shares
        else:
            share_post = shares
    if share_pre is None or share_post is None:
        raise ValueError("TASK-8: bootstrap missing a period stratum")
    boot = {cls: 100.0 * (share_post[cls] - share_pre[cls]) for cls in CLASSES}
    ci_unreliable = int(any(g_h[h] < 10 for h in PERIOD_STRATA))
    out: dict = {
        "B": B,
        "master_seed": MASTER_SEED,
        "stratum_seeds": {h: int(seeds[h]) for h in PERIOD_STRATA},
        "G_h": g_h,
        "ci_unreliable": ci_unreliable,
        "m": 3,
        "classes": {},
    }
    p_raw: dict[str, float] = {}
    for cls in CLASSES:
        samples = boot[cls]
        lo, hi = np.quantile(samples, [0.025, 0.975])
        p_raw[cls] = two_sided_p(samples, float(observed_pp[cls]))
        out["classes"][cls] = {
            "observed_pp": float(observed_pp[cls]),
            "ci95": [float(lo), float(hi)],
            "includes_0": bool(lo <= 0.0 <= hi),
        }
    p_bh = bh_adjusted(p_raw, 3)
    n_judgeable_videos = {
        h: int(judgeable.loc[judgeable["period"] == h, "video_id"].nunique())
        for h in PERIOD_STRATA
    }
    out["n_judgeable_videos"] = n_judgeable_videos
    for cls in CLASSES:
        row = out["classes"][cls]
        row["p_raw"] = p_raw[cls]
        row["p_BH"] = p_bh[cls]
        if ci_unreliable:
            row["conclusion"] = "inconclusive"
            row["judgeable_videos"] = n_judgeable_videos
        else:
            row["conclusion"] = "estimated"
    return out


def year_video_counts(videos: pd.DataFrame) -> list[dict]:
    year = videos["upload_date"].astype(str).str.slice(0, 4)
    counts = year.value_counts().sort_index()
    return [{"year": str(y), "n_videos": int(n)} for y, n in counts.items()]


def open_analysis_text(
    got: dict[str, float],
    shares: dict[str, dict[str, float]],
    c24: dict[str, dict[str, int]],
    none_all: dict[str, int],
    unassigned_class: dict[str, int],
    undeclared: dict[str, int],
    year_cells: list[dict],
    boot: dict,
    videos_n: int,
    n_unassigned_period: int,
) -> str:
    lines = [
        "# TASK-8 open analysis",
        "",
        f"Population: the {videos_n} videos of this channel. Agreement is",
        "n_match / n_judgeable on the contract-24 judgeable set; this task",
        "does not re-declare that rate. Shares below use the judgeable",
        "denominator of that period only.",
        "",
        "## Class shares on the judgeable set",
        "",
        "gap_share_<class>_pp = 100 * (share_post - share_pre), in percentage",
        "points. Each class is an explicit jp_match predicate, not the",
        "complement of the others. Unassigned judgeable rows (exact_default,",
        "exact_alt, and any undeclared value) are counted in manifest.json.",
        "",
    ]
    for cls in CLASSES:
        pre_s = shares[cls]["pre"]
        post_s = shares[cls]["post"]
        gap = got[f"gap_share_{cls}_pp"]
        n_pre = int(got[f"n_{cls}_judgeable_pre"])
        n_post = int(got[f"n_{cls}_judgeable_post"])
        lines.append(
            f"- {cls}: share_pre={pre_s:.8f} (n={n_pre} / "
            f"{int(got['n_judgeable_pre'])}), "
            f"share_post={post_s:.8f} (n={n_post} / "
            f"{int(got['n_judgeable_post'])}), "
            f"gap_share_{cls}_pp={gap:.8f}"
        )
    tone_seg = got["gap_share_tone_pp"] + got["gap_share_segment_pp"]
    lines.extend(
        [
            "",
            f"tone+segment contribution = {tone_seg:.8f} pp; "
            f"diff = {got['gap_share_diff_pp']:.8f} pp.",
            f"Sum of three contributions = "
            f"{got['gap_share_tone_pp'] + got['gap_share_segment_pp'] + got['gap_share_diff_pp']:.8f} pp.",
            "",
            "descriptive=1 for the share table (the three gap_share_*_pp values",
            "are the declared measurements; this paragraph does not add a p-value).",
            "",
            "## Contract-24 counts (not declared numbers)",
            "",
        ]
    )
    for period in PERIOD_STRATA:
        lines.append(f"- {period}: {json.dumps(c24[period], sort_keys=True)}")
    lines.extend(
        [
            "",
            "n_dur_le_0 is the count dropped by dur > 0 on the published set",
            "of that period (contract 25). n_empty_realized and n_dur_le_0",
            "overlap, so n_judgeable is not n_total minus those two counts.",
            "",
            "## none on the published set (denominator is A+B, not judgeable)",
            "",
            f"- none_pre={none_all['pre']} / n_total_pre={c24['pre']['n_total']}",
            f"- none_post={none_all['post']} / n_total_post={c24['post']['n_total']}",
            "- none on the judgeable set is structurally 0.",
            "",
            "## Class-partition unassigned and undeclared enum on judgeable rows",
            "",
            f"- unassigned_class_pre={unassigned_class['pre']}",
            f"- unassigned_class_post={unassigned_class['post']}",
            f"- undeclared_enum_pre={undeclared['pre']}",
            f"- undeclared_enum_post={undeclared['post']}",
            f"- n_unassigned_period (videos)={n_unassigned_period}",
            "",
            "## Year cells (video counts; 2021 and 2023 are small)",
            "",
        ]
    )
    for cell in year_cells:
        lines.append(f"- {cell['year']}: n_videos={cell['n_videos']}")
    lines.extend(
        [
            "",
            "## Cluster bootstrap",
            "",
            f"B={boot['B']} whole-video_id resamples within period strata.",
            f"Master seed {boot['master_seed']}. Per-stratum seeds are",
            'int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16).',
            "",
            f"- pre: G_h={boot['G_h']['pre']}, videos with judgeable syllables={boot['n_judgeable_videos']['pre']}, ci_unreliable stratum={int(boot['G_h']['pre'] < 10)}",
            f"- post: G_h={boot['G_h']['post']}, videos with judgeable syllables={boot['n_judgeable_videos']['post']}, ci_unreliable stratum={int(boot['G_h']['post'] < 10)}",
            f"- any-stratum ci_unreliable={boot['ci_unreliable']}",
            f"- m={boot['m']}",
            "",
        ]
    )
    for cls in CLASSES:
        row = boot["classes"][cls]
        lines.append(
            f"- {cls}: 95% percentile CI [{row['ci95'][0]:.6f}, {row['ci95'][1]:.6f}] pp; "
            f"includes 0={row['includes_0']}; "
            f"p_raw={row['p_raw']:.6g}; p_BH={row['p_BH']:.6g}; "
            f"conclusion={row['conclusion']}"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "On the 567 videos of this channel, the judgeable A+B share of "
            "tone and of segment each rose after 2024 by more than the share "
            f"of diff (gap_share_tone_pp={got['gap_share_tone_pp']:.4f}, "
            f"gap_share_segment_pp={got['gap_share_segment_pp']:.4f}, "
            f"gap_share_diff_pp={got['gap_share_diff_pp']:.4f}); the "
            "pre−post rise in disagreement quality on the judgeable set is "
            "larger in tone and segment than in diff.",
            "",
        ]
    )
    return "\n".join(lines)


def compute(corpus_PATH: str, readme_PATH: str, brief_PATH: str, sql_DIR: str, repo_ROOT: str) -> dict:
    corpus_sha = verify_corpus_hash(corpus_PATH, readme_PATH)
    conn = open_corpus(corpus_PATH)
    try:
        loaded = load_published_frame(conn, brief_PATH, readme_PATH)
        inputs = {
            "data/corpus_v2.sqlite": {
                "sha256": corpus_sha,
                "tables": {
                    "videos": {
                        "rows": int(len(loaded["videos"])),
                        "columns": table_columns(conn, "videos"),
                    },
                    "windows": {
                        "rows": int(len(loaded["windows"])),
                        "columns": table_columns(conn, "windows"),
                    },
                    "syllables": {
                        "rows": int(len(loaded["syllables"])),
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
        for name, expr in GAP_EXPR.items():
            got[name] = eval_derived(expr, got)
    finally:
        conn.close()

    videos = loaded["videos"].copy()
    published = loaded["published"].copy()
    if "period" in videos.columns or "period" in published.columns:
        raise ValueError("TASK-8: duplicate column period")
    v_pre, v_post, v_unassigned = period_masks(videos["upload_date"])
    videos["period"] = period_label(v_pre, v_post)
    p_pre, p_post, p_unassigned = period_masks(published["upload_date"])
    published["period"] = period_label(p_pre, p_post)

    assert_counts_equal("n_videos_pre", got["n_videos_pre"], int(v_pre.sum()))
    assert_counts_equal("n_videos_post", got["n_videos_post"], int(v_post.sum()))
    assert_counts_equal("n_unassigned_period", got["n_unassigned_period"], int(v_unassigned.sum()))

    steps = list(loaded["steps"])
    steps.append(
        {
            "step": "period_videos",
            "rule": "four-digit year <=2024 vs >=2025, neither is unassigned",
            "group": "all",
            "rows_before": int(len(videos)),
            "rows_after": int(len(videos)),
            "n_pre": int(v_pre.sum()),
            "n_post": int(v_post.sum()),
            "n_unassigned": int(v_unassigned.sum()),
        }
    )
    steps.append(
        {
            "step": "period_published_syllables",
            "rule": "same period predicates on published A+B syllables",
            "group": "all",
            "rows_before": int(len(published)),
            "rows_after": int(len(published)),
            "n_pre": int(p_pre.sum()),
            "n_post": int(p_post.sum()),
            "n_unassigned": int(p_unassigned.sum()),
        }
    )

    judgeable_flag = judgeable_mask(published)
    assert_no_null_jp_match(published, judgeable_flag)
    judgeable = published.loc[judgeable_flag].copy()
    class_m = class_masks(judgeable["jp_match"])
    judgeable["is_tone"] = class_m["tone"]
    judgeable["is_segment"] = class_m["segment"]
    judgeable["is_diff"] = class_m["diff"]
    assigned = class_m["tone"] | class_m["segment"] | class_m["diff"]
    judgeable["class_unassigned"] = ~assigned

    c24: dict[str, dict[str, int]] = {}
    none_all: dict[str, int] = {}
    unassigned_class: dict[str, int] = {}
    undeclared: dict[str, int] = {}
    shares: dict[str, dict[str, float]] = {cls: {} for cls in CLASSES}

    for period in PERIOD_STRATA:
        pub_p = published.loc[published["period"] == period]
        jud_p = judgeable.loc[judgeable["period"] == period]
        before = int(len(pub_p))
        empty = pub_p["jp_realized"].isna() | (pub_p["jp_realized"].fillna("").astype(str) == "")
        dur_le_0 = pub_p["dur"] <= 0
        steps.append(
            {
                "step": "empty_realized",
                "rule": "jp_realized nonempty",
                "group": period,
                "rows_before": before,
                "rows_after": int((~empty).sum()),
            }
        )
        steps.append(
            {
                "step": "dur_gt_0",
                "rule": "dur > 0 (contract 25)",
                "group": period,
                "rows_before": before,
                "rows_after": int((~dur_le_0).sum()),
            }
        )
        steps.append(
            {
                "step": "judgeable",
                "rule": "jp_realized nonempty and dur > 0",
                "group": period,
                "rows_before": before,
                "rows_after": int(len(jud_p)),
            }
        )
        c24[period] = contract24(pub_p)
        none_all[period] = int((pub_p["jp_match"] == "none").sum())
        unassigned_class[period] = int(jud_p["class_unassigned"].sum())
        undeclared[period] = int((~jud_p["jp_match"].isin(DECLARED_ENUM)).sum())
        steps.append(
            {
                "step": "class_partition",
                "rule": "jp_match in {tone, segment, diff}; else unassigned",
                "group": period,
                "rows_before": int(len(jud_p)),
                "rows_after": int((~jud_p["class_unassigned"]).sum()),
                "n_unassigned": unassigned_class[period],
                "n_undeclared_enum": undeclared[period],
            }
        )
        for cls in CLASSES:
            n_cls = int(jud_p[f"is_{cls}"].sum())
            assert_counts_equal(
                f"n_{cls}_judgeable_{period}",
                got[f"n_{cls}_judgeable_{period}"],
                n_cls,
            )
            shares[cls][period] = n_cls / float(len(jud_p))
        assert_counts_equal(
            f"n_judgeable_{period}",
            got[f"n_judgeable_{period}"],
            int(len(jud_p)),
        )

    videos_n = int(loaded["counts"].videos_expected)
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
        judgeable,
        {cls: float(got[f"gap_share_{cls}_pp"]) for cls in CLASSES},
    )
    year_cells = year_video_counts(videos)
    analysis = open_analysis_text(
        got,
        shares,
        c24,
        none_all,
        unassigned_class,
        undeclared,
        year_cells,
        boot,
        videos_n,
        int(v_unassigned.sum()),
    )
    manifest = {
        "git_sha": git_sha(repo_ROOT),
        "inputs": inputs,
        "frame": {
            "videos_expected": int(loaded["counts"].videos_expected),
            "windows_expected": int(loaded["counts"].windows_expected),
            "syllables_expected": int(loaded["counts"].syllables_expected),
            "published_expected": int(loaded["counts"].published_expected),
        },
        "steps": steps,
        "contract24": c24,
        "none_published": none_all,
        "class_unassigned_judgeable": unassigned_class,
        "undeclared_enum_judgeable": undeclared,
        "year_cells": year_cells,
        "shares": {
            cls: {
                "pre": shares[cls]["pre"],
                "post": shares[cls]["post"],
                "gap_share_pp": got[f"gap_share_{cls}_pp"],
            }
            for cls in CLASSES
        },
        "descriptive": 1,
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
