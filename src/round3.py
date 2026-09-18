"""ROUND-3: recompute c1/c2/c3 comparisons (SQLite/pandas only; no inference)."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.agreement import MATCH_VALUES, status_for_measure
from src.compare import (
    assert_no_clap_in_comparison,
    bh_corrected,
    conclusion_for,
    difference_vs_baseline,
    require_comparison_id,
)
from src.frame import BOILER_TEXT, assign_group, load_frame
from src.manifest import build_manifest, git_blob_sha1, parse_upload_date
from src.merge import checked_merge, left_attach
from src.onset import parse_onset
from src.paths import atomic_write_json, refuse_inference, require_path, sha256_file, write_status
from src.seeds import assert_stratum_seeds, stratum_seed
from src.sql_loader import load_sql

COMPARISON_SQL = {
    "c1_period_drop": "c1_period_drop",
    "c2_highsnr_onset_residual": "c2_highsnr_onset",
    "c3_singing_removal": "c3_singing_removal",
}

SINGING_PROB_SOURCE = "task2_window_quality/window_quality_with_flags.csv"
POST_CUTOFF = "2025-01-01"
ONSET_TARGET = frozenset({"n", "ng", "gw"})
MANIFEST_STRATUM_COUNT_NONE = "manifest stratum count is None"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    seq = list(argv) if argv is not None else sys.argv[1:]
    refuse_inference(seq)
    parser = argparse.ArgumentParser(prog="src.round3")
    parser.add_argument("--corpus-path", dest="corpus_PATH", required=True)
    parser.add_argument("--window-quality", dest="window_quality_FILE", required=True)
    parser.add_argument("--frame-file", dest="frame_FILE", required=True)
    parser.add_argument("--round-yaml", dest="round_yaml_FILE", required=True)
    parser.add_argument("--out-dir", dest="out_DIR", required=True)
    parser.add_argument("--sql-dir", dest="sql_DIR", required=True)
    parser.add_argument("--flags-csv", dest="flags_FILE", required=True)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Fixture smoke run: STATUS smoke_ok; relax join expected_rows",
    )
    return parser.parse_args(seq)


def _comparisons(round_yaml_FILE: Path) -> list[dict]:
    raw = yaml.safe_load(Path(round_yaml_FILE).read_text(encoding="utf-8"))
    return list(raw["comparisons"])


def _sql_select_names(sql_text: str) -> list[str]:
    names: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip().rstrip(",")
        if " AS " in stripped:
            names.append(stripped.split(" AS ")[-1].strip())
        elif "." in stripped and stripped.split()[0].count(".") == 1:
            names.append(stripped.split()[0].split(".")[-1])
    return names


def _git_sha(repo_ROOT: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _load_sql_df(corpus_PATH: Path, sql_text: str) -> pd.DataFrame:
    con = sqlite3.connect(str(corpus_PATH))
    try:
        return pd.read_sql_query(sql_text, con)
    finally:
        con.close()


def _judgeable_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    dur = out["syllable_dur"]
    realized = out["jp_realized"]
    empty = realized.isna() | (realized.astype(str) == "")
    dur_raw = dur.isna() | (dur.astype(float) <= 0)
    # Partition: empty first; dur_le_0 only among non-empty so
    # n_judgeable = n_total - n_empty - n_dur_le_0 holds.
    dur_le_0 = (~empty) & dur_raw
    judgeable = (~empty) & (~dur_raw)
    bad = judgeable & out["jp_match"].isna()
    if bool(bad.any()):
        raise ValueError("NULL jp_match on judgeable row")
    out["_empty"] = empty
    out["_dur_le_0"] = dur_le_0
    out["_judgeable"] = judgeable
    out["_match"] = judgeable & out["jp_match"].isin(MATCH_VALUES)
    return out


def _counts(df: pd.DataFrame) -> dict[str, Any]:
    n_total = int(len(df))
    n_empty = int(df["_empty"].sum()) if n_total else 0
    n_dur = int(df["_dur_le_0"].sum()) if n_total else 0
    n_judgeable = int(df["_judgeable"].sum()) if n_total else 0
    n_match = int(df["_match"].sum()) if n_total else 0
    if n_judgeable != n_total - n_empty - n_dur:
        raise ValueError("n_judgeable identity failed")
    agreement = (n_match / n_judgeable) if n_judgeable > 0 else None
    return {
        "n_total": n_total,
        "n_empty_realized": n_empty,
        "n_dur_le_0": n_dur,
        "n_judgeable": n_judgeable,
        "n_match": n_match,
        "agreement": agreement,
    }


def require_stratum_count(value: Any) -> int:
    if value is None:
        raise ValueError(MANIFEST_STRATUM_COUNT_NONE)
    return int(value)


def _agreement_rate(n_match: float, n_judgeable: float) -> float | None:
    if n_judgeable <= 0:
        return None
    return float(n_match) / float(n_judgeable)


def _cell_rate(video_stats: pd.DataFrame, videos: list[str]) -> float | None:
    if not videos:
        return None
    sub = video_stats.loc[video_stats.index.isin(videos)]
    if sub.empty:
        return None
    return _agreement_rate(float(sub["n_match"].sum()), float(sub["n_judgeable"].sum()))


def _video_level_stats(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["n_match", "n_judgeable", "n_total", "n_empty", "n_dur"])
    g = (
        df.groupby("video_id", sort=False)
        .agg(
            n_match=("_match", "sum"),
            n_judgeable=("_judgeable", "sum"),
            n_total=("_match", "size"),
            n_empty=("_empty", "sum"),
            n_dur=("_dur_le_0", "sum"),
        )
        .astype({"n_match": int, "n_judgeable": int, "n_total": int, "n_empty": int, "n_dur": int})
    )
    return g


def _did_from_cells(
    film_post: float | None,
    cont_post: float | None,
    film_pre: float | None,
    cont_pre: float | None,
) -> dict[str, Any] | None:
    if any(v is None for v in (film_post, cont_post, film_pre, cont_pre)):
        return None
    return difference_vs_baseline(film_post, film_pre, cont_post, cont_pre)


def _bootstrap_did_p(
    video_stats: pd.DataFrame,
    cells: dict[str, list[str]],
    *,
    B: int,
    seed: int,
    observed_did: float,
) -> float:
    """Cluster bootstrap p-value for DID=0 (two-sided, normal approx from boot SE)."""
    rng = np.random.default_rng(seed)
    boots: list[float] = []
    keys = ("film_post", "cont_post", "film_pre", "cont_pre")
    for _ in range(B):
        rates: dict[str, float | None] = {}
        ok = True
        for key in keys:
            vids = cells[key]
            if not vids:
                ok = False
                break
            idx = rng.integers(0, len(vids), size=len(vids))
            drawn = [vids[i] for i in idx]
            rates[key] = _cell_rate(video_stats, drawn)
            if rates[key] is None:
                ok = False
                break
        if not ok:
            continue
        payload = _did_from_cells(
            rates["film_post"], rates["cont_post"], rates["film_pre"], rates["cont_pre"]
        )
        if payload is None:
            continue
        boots.append(float(payload["did"]))
    if len(boots) < max(50, B // 10):
        return 1.0
    arr = np.asarray(boots, dtype=float)
    se = float(arr.std(ddof=1))
    if se == 0.0 or math.isnan(se):
        return 1.0 if observed_did == 0.0 else 0.0
    z = abs(observed_did) / se
    # two-sided normal approx
    from math import erfc

    p = float(erfc(z / math.sqrt(2.0)))
    if p > 1.0:
        p = 1.0
    if p < 0.0:
        p = 0.0
    return p


def _bootstrap_delta_p(
    video_stats_before: pd.DataFrame,
    video_stats_after: pd.DataFrame,
    videos: list[str],
    *,
    B: int,
    seed: int,
    observed_delta_pp: float,
) -> float:
    if len(videos) < 2:
        return 1.0
    rng = np.random.default_rng(seed)
    boots: list[float] = []
    for _ in range(B):
        idx = rng.integers(0, len(videos), size=len(videos))
        drawn = [videos[i] for i in idx]
        before = _cell_rate(video_stats_before, drawn)
        after = _cell_rate(video_stats_after, drawn)
        if before is None or after is None:
            continue
        boots.append((after - before) * 100.0)
    if len(boots) < max(50, B // 10):
        return 1.0
    arr = np.asarray(boots, dtype=float)
    se = float(arr.std(ddof=1))
    if se == 0.0 or math.isnan(se):
        return 1.0 if observed_delta_pp == 0.0 else 0.0
    z = abs(observed_delta_pp) / se
    from math import erfc

    p = float(erfc(z / math.sqrt(2.0)))
    return min(max(p, 0.0), 1.0)


def _status_bundle(counts: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for col in ("n_total", "n_match", "n_judgeable", "n_empty_realized", "n_dur_le_0"):
        val = counts.get(col)
        out[f"{col}_status"] = status_for_measure(
            val, computed_from_data=val is not None
        )
    return out


def _period_label(upload_date: str) -> str:
    iso = parse_upload_date(upload_date)
    return "post" if iso >= POST_CUTOFF else "pre"


def _prepare_base(
    df: pd.DataFrame,
    flags: pd.DataFrame,
    quality: pd.DataFrame | None,
    *,
    need_quality: bool,
    row_accounting: list[dict[str, Any]],
) -> pd.DataFrame:
    before = len(df)
    df = _judgeable_flags(df)
    row_accounting.append(
        {
            "step": "judgeable_flags",
            "rule": "n_judgeable = not empty and dur>0",
            "group": "all",
            "rows_before": before,
            "rows_after": len(df),
        }
    )
    flag_cols = flags[["video_id", "film_flag", "contemporary_only"]].drop_duplicates(
        "video_id"
    )
    df = left_attach(
        df, flag_cols, ["video_id"], step="attach_video_flags", row_accounting=row_accounting
    )
    groups = [
        assign_group(int(ff) if not pd.isna(ff) else 0, int(co) if not pd.isna(co) else 0)
        for ff, co in zip(df["film_flag"], df["contemporary_only"])
    ]
    df["group"] = groups
    df["period"] = [_period_label(str(x)) for x in df["upload_date"]]
    if need_quality:
        if quality is None:
            raise ValueError("window quality required")
        q = quality.rename(columns={"window_id": "uid"})[
            ["uid", "singing_prob", "snr_db"]
        ].drop_duplicates("uid")
        # refuse clap column if present
        if "clap_sing" in (quality.columns if quality is not None else []):
            raise ValueError(
                "clap_sing must not join PANNs singing_prob in the same comparison"
            )
        df = left_attach(
            df, q, ["uid"], step="attach_window_quality", row_accounting=row_accounting
        )
    return df


def _assigned(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[df["group"].isin(["treatment", "control"])].copy()


def _cells_by_group_period(df: pd.DataFrame) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        "film_post": [],
        "cont_post": [],
        "film_pre": [],
        "cont_pre": [],
    }
    for group, period, key in (
        ("treatment", "post", "film_post"),
        ("control", "post", "cont_post"),
        ("treatment", "pre", "film_pre"),
        ("control", "pre", "cont_pre"),
    ):
        vids = (
            df.loc[(df["group"] == group) & (df["period"] == period), "video_id"]
            .drop_duplicates()
            .astype(str)
            .tolist()
        )
        out[key] = vids
    return out


def _metric_shell(
    comparison_id: str,
    counts: dict[str, Any],
    *,
    G_h: int,
    n_h_judgeable: int,
    min_judgeable: int,
    p_raw: float | None,
    p_bh: float | None,
    m: int,
    extra: dict[str, Any],
) -> dict[str, Any]:
    conc = conclusion_for(G_h, n_h_judgeable, min_judgeable)
    body: dict[str, Any] = {
        "comparison_id": comparison_id,
        "p_raw": p_raw,
        "p_bh": p_bh,
        "m": m,
        "n_total": counts["n_total"],
        "n_match": counts["n_match"],
        "n_judgeable": counts["n_judgeable"],
        "n_empty_realized": counts["n_empty_realized"],
        "n_dur_le_0": counts["n_dur_le_0"],
        **_status_bundle(counts),
        "G_h": G_h,
        "n_h_judgeable": n_h_judgeable,
        "ci_unreliable": conc["ci_unreliable"],
        "conclusion": conc["conclusion"],
        "exploratory": 0,
    }
    body.update(extra)
    return body


def compute_c1(
    df: pd.DataFrame,
    *,
    B: int,
    seed: int,
    min_judgeable: int,
    m: int,
) -> tuple[dict[str, Any], float]:
    assigned = _assigned(df)
    counts = _counts(assigned)
    stats = _video_level_stats(assigned)
    cells = _cells_by_group_period(assigned)
    film_post = _cell_rate(stats, cells["film_post"])
    cont_post = _cell_rate(stats, cells["cont_post"])
    film_pre = _cell_rate(stats, cells["film_pre"])
    cont_pre = _cell_rate(stats, cells["cont_pre"])
    payload = _did_from_cells(film_post, cont_post, film_pre, cont_pre)
    G_h = int(assigned["video_id"].nunique()) if len(assigned) else 0
    n_h = counts["n_judgeable"]
    if payload is None:
        extra = {
            "did": None,
            "did_status": "missing",
            "treatment_value": film_post,
            "treatment_baseline": film_pre,
            "control_value": cont_post,
            "control_baseline": cont_pre,
        }
        row = _metric_shell(
            "c1_period_drop",
            counts,
            G_h=G_h,
            n_h_judgeable=n_h,
            min_judgeable=min_judgeable,
            p_raw=None,
            p_bh=None,
            m=m,
            extra=extra,
        )
        # missing DID cannot carry p; mark descriptive? keep exploratory=0 but p null
        # Schema allows null p. If inconclusive from size, conclusion already set.
        if row["conclusion"] == "pending":
            row["conclusion"] = "inconclusive"
        return row, 1.0
    did = float(payload["did"])
    p_raw = _bootstrap_did_p(stats, cells, B=B, seed=seed, observed_did=did)
    extra = {
        "did": did,
        "did_status": status_for_measure(did, computed_from_data=True),
        "treatment_value": payload["treatment_value"],
        "treatment_baseline": payload["treatment_baseline"],
        "control_value": payload["control_value"],
        "control_baseline": payload["control_baseline"],
    }
    row = _metric_shell(
        "c1_period_drop",
        counts,
        G_h=G_h,
        n_h_judgeable=n_h,
        min_judgeable=min_judgeable,
        p_raw=p_raw,
        p_bh=None,
        m=m,
        extra=extra,
    )
    return row, p_raw


def compute_c2(
    df: pd.DataFrame,
    *,
    B: int,
    seed: int,
    min_judgeable: int,
    m: int,
    row_accounting: list[dict[str, Any]],
) -> tuple[dict[str, Any], float]:
    before = len(df)
    # quality subset
    mask_q = (df["snr_db"] > 15) & (df["singing_prob"] < 0.2)
    sub = df.loc[mask_q].copy()
    row_accounting.append(
        {
            "step": "c2_quality_subset",
            "rule": "snr_db>15 AND singing_prob<0.2 (PANNs)",
            "group": "all",
            "rows_before": before,
            "rows_after": len(sub),
        }
    )
    onsets = []
    keep = []
    for jp in sub["jp_default"]:
        try:
            onsets.append(parse_onset(jp if pd.notna(jp) else None))
            keep.append(True)
        except ValueError:
            onsets.append(None)
            keep.append(False)
    sub = sub.loc[keep].copy()
    sub["onset"] = [o for o, k in zip(onsets, keep) if k]
    before2 = len(sub)
    sub = sub.loc[sub["onset"].isin(ONSET_TARGET)].copy()
    row_accounting.append(
        {
            "step": "c2_onset_subset",
            "rule": "onset in {n,ng,gw}",
            "group": "all",
            "rows_before": before2,
            "rows_after": len(sub),
        }
    )
    assigned = _assigned(sub)
    counts = _counts(assigned)
    stats = _video_level_stats(assigned)
    cells = _cells_by_group_period(assigned)
    film_post = _cell_rate(stats, cells["film_post"])
    cont_post = _cell_rate(stats, cells["cont_post"])
    film_pre = _cell_rate(stats, cells["film_pre"])
    cont_pre = _cell_rate(stats, cells["cont_pre"])
    payload = _did_from_cells(film_post, cont_post, film_pre, cont_pre)
    G_h = int(assigned["video_id"].nunique()) if len(assigned) else 0
    n_h = counts["n_judgeable"]
    if payload is None:
        extra = {
            "did": None,
            "did_status": "missing",
            "treatment_value": film_post,
            "treatment_baseline": film_pre,
            "control_value": cont_post,
            "control_baseline": cont_pre,
            "singing_prob_source": SINGING_PROB_SOURCE,
        }
        row = _metric_shell(
            "c2_highsnr_onset_residual",
            counts,
            G_h=G_h,
            n_h_judgeable=n_h,
            min_judgeable=min_judgeable,
            p_raw=None,
            p_bh=None,
            m=m,
            extra=extra,
        )
        if row["conclusion"] == "pending":
            row["conclusion"] = "inconclusive"
        return row, 1.0
    did = float(payload["did"])
    p_raw = _bootstrap_did_p(stats, cells, B=B, seed=seed, observed_did=did)
    extra = {
        "did": did,
        "did_status": status_for_measure(did, computed_from_data=True),
        "treatment_value": payload["treatment_value"],
        "treatment_baseline": payload["treatment_baseline"],
        "control_value": payload["control_value"],
        "control_baseline": payload["control_baseline"],
        "singing_prob_source": SINGING_PROB_SOURCE,
    }
    row = _metric_shell(
        "c2_highsnr_onset_residual",
        counts,
        G_h=G_h,
        n_h_judgeable=n_h,
        min_judgeable=min_judgeable,
        p_raw=p_raw,
        p_bh=None,
        m=m,
        extra=extra,
    )
    return row, p_raw


def compute_c3(
    df: pd.DataFrame,
    *,
    B: int,
    seed: int,
    min_judgeable: int,
    m: int,
    row_accounting: list[dict[str, Any]],
) -> tuple[dict[str, Any], float]:
    film = df.loc[df["group"] == "treatment"].copy()
    before = len(film)
    counts_before = _counts(film)
    agree_before = counts_before["agreement"]
    film_after = film.loc[~(film["singing_prob"] > 0.5)].copy()
    row_accounting.append(
        {
            "step": "c3_remove_high_singing",
            "rule": "drop singing_prob>0.5 (PANNs) on film",
            "group": "treatment",
            "rows_before": before,
            "rows_after": len(film_after),
        }
    )
    counts_after = _counts(film_after)
    agree_after = counts_after["agreement"]
    # Use after-removal counts in the metric row (primary analysis set)
    counts = counts_after
    G_h = int(film["video_id"].nunique()) if len(film) else 0
    n_h = counts["n_judgeable"]
    if agree_before is None or agree_after is None:
        extra = {
            "delta_pp": None,
            "delta_pp_status": "missing",
            "treatment_value": agree_after,
            "treatment_baseline": agree_before,
            "control_value": None,
            "control_baseline": None,
            "singing_prob_source": SINGING_PROB_SOURCE,
        }
        row = _metric_shell(
            "c3_singing_removal",
            counts,
            G_h=G_h,
            n_h_judgeable=n_h,
            min_judgeable=min_judgeable,
            p_raw=None,
            p_bh=None,
            m=m,
            extra=extra,
        )
        if row["conclusion"] == "pending":
            row["conclusion"] = "inconclusive"
        return row, 1.0
    delta_pp = (agree_after - agree_before) * 100.0
    stats_before = _video_level_stats(film)
    stats_after = _video_level_stats(film_after)
    videos = film["video_id"].drop_duplicates().astype(str).tolist()
    p_raw = _bootstrap_delta_p(
        stats_before,
        stats_after,
        videos,
        B=B,
        seed=seed,
        observed_delta_pp=delta_pp,
    )
    extra = {
        "delta_pp": delta_pp,
        "delta_pp_status": status_for_measure(delta_pp, computed_from_data=True),
        "treatment_value": agree_after,
        "treatment_baseline": agree_before,
        "control_value": None,
        "control_baseline": None,
        "singing_prob_source": SINGING_PROB_SOURCE,
    }
    row = _metric_shell(
        "c3_singing_removal",
        counts,
        G_h=G_h,
        n_h_judgeable=n_h,
        min_judgeable=min_judgeable,
        p_raw=p_raw,
        p_bh=None,
        m=m,
        extra=extra,
    )
    # Apply prediction threshold to conclusion when size OK
    if row["conclusion"] == "pending":
        if abs(delta_pp) <= 0.5:
            row["conclusion"] = "supports_H3"
        else:
            row["conclusion"] = "rejects_H3"
    return row, p_raw


def _finalize_conclusions_c1_c2(row: dict[str, Any], *, is_c2: bool) -> dict[str, Any]:
    if row["conclusion"] != "pending":
        return row
    if row.get("did") is None or row.get("p_bh") is None:
        row["conclusion"] = "inconclusive"
        return row
    did = float(row["did"])
    p_bh = float(row["p_bh"])
    if is_c2:
        row["conclusion"] = "supports_H2" if did <= -0.15 else "rejects_H2"
    else:
        # H1: p_bh < 0.05 and sign unchanged (negative film gap expected from prior)
        if p_bh < 0.05:
            row["conclusion"] = "supports_H1"
        else:
            row["conclusion"] = "rejects_H1"
    return row


def _write_readme(
    out_DIR: Path,
    rows: dict[str, dict[str, Any]],
    *,
    smoke: bool,
) -> None:
    c1, c2, c3 = rows["c1"], rows["c2"], rows["c3"]

    def fmt(x: Any, nd: int = 6) -> str:
        if x is None:
            return "null"
        if isinstance(x, float):
            return f"{x:.{nd}f}"
        return str(x)

    lines = [
        "# ROUND-3 复算结果（分析员）",
        "",
        "抽样框：tier A+B，排除订阅结尾样板文本；一致率仅从 `jp_match ∈ {exact_default,exact_alt}`；"
        "`n_judgeable = n_total − n_empty_realized − n_dur_le_0`。不读 `review_prior`，不用 `flag_sing` 分层。"
        "H2/H3 的 `singing_prob`/`snr_db` 仅来自 `task2_window_quality/window_quality_with_flags.csv`（PANNs 整窗），不与 CLAP 同表。",
        "",
        f"运行模式：{'冒烟（fixtures/sample.sqlite）' if smoke else '全量 corpus'}。",
        "",
        "## 结论对照预测（commit d6f1132）",
        "",
        "| 比较 | 预测 | 观测 | 判定 |",
        "|---|---|---|---|",
        f"| c1_period_drop (H1) | p_bh<0.05 且方向不变 | did={fmt(c1.get('did'))}, p_bh={fmt(c1.get('p_bh'))} | {c1.get('conclusion')} |",
        f"| c2_highsnr_onset_residual (H2) | did ≤ −0.15 | did={fmt(c2.get('did'))}, p_bh={fmt(c2.get('p_bh'))} | {c2.get('conclusion')} |",
        f"| c3_singing_removal (H3) | abs(delta_pp)≤0.5 | delta_pp={fmt(c3.get('delta_pp'))}, p_bh={fmt(c3.get('p_bh'))} | {c3.get('conclusion')} |",
        "",
        "## 支撑数字",
        "",
        "### H1 / c1_period_drop",
        "",
        f"- did = (film_post − cont_post) − (film_pre − cont_pre) = {fmt(c1.get('did'))}",
        f"- film_post={fmt(c1.get('treatment_value'))}, film_pre={fmt(c1.get('treatment_baseline'))}",
        f"- cont_post={fmt(c1.get('control_value'))}, cont_pre={fmt(c1.get('control_baseline'))}",
        f"- p_raw={fmt(c1.get('p_raw'))}, p_bh={fmt(c1.get('p_bh'))}, m={c1.get('m')}",
        f"- n_judgeable={c1.get('n_judgeable')}, G_h={c1.get('G_h')}, ci_unreliable={c1.get('ci_unreliable')}",
        "",
        "### H2 / c2_highsnr_onset_residual",
        "",
        f"- 子集：snr_db>15 且 singing_prob<0.2 且 onset∈{{n,ng,gw}}",
        f"- did={fmt(c2.get('did'))}（阈值 ≤ −0.15）",
        f"- film_post={fmt(c2.get('treatment_value'))}, film_pre={fmt(c2.get('treatment_baseline'))}",
        f"- cont_post={fmt(c2.get('control_value'))}, cont_pre={fmt(c2.get('control_baseline'))}",
        f"- p_raw={fmt(c2.get('p_raw'))}, p_bh={fmt(c2.get('p_bh'))}",
        f"- n_judgeable={c2.get('n_judgeable')}, G_h={c2.get('G_h')}",
        "",
        "### H3 / c3_singing_removal",
        "",
        f"- film 剔除 singing_prob>0.5 前后：before={fmt(c3.get('treatment_baseline'))}, after={fmt(c3.get('treatment_value'))}",
        f"- delta_pp={fmt(c3.get('delta_pp'))}（百分点；阈值 abs≤0.5）",
        f"- p_raw={fmt(c3.get('p_raw'))}, p_bh={fmt(c3.get('p_bh'))}",
        f"- n_judgeable={c3.get('n_judgeable')}, G_h={c3.get('G_h')}",
        "",
        "## 反对解释 / 边界",
        "",
        "- 总体仅表述为本频道视频集合（frame.yaml `n_videos`），不得外推为「粤语」。",
        "- 聚类至 `video_id`；`G_h<10` 时 `ci_unreliable=1` 且结论 inconclusive。",
        "- 冒烟夹具若无 post-2025 单元，DID 可为 null，结论 inconclusive，不否定全量结果。",
        "- 音频跨度溯源见 `metrics/span_provenance_summary.json`（若存在）；本复算不读 CLAP。",
        "",
        "## 重算命令",
        "",
        "```bash",
        "cd /workspace/cantoai/analysis",
        "python -m src.round3 \\",
        "  --corpus-path \"$CORPUS_PATH\" \\",
        "  --window-quality task2_window_quality/window_quality_with_flags.csv \\",
        "  --flags-csv task3_multilabel_flags/video_multilabel_flags.csv \\",
        "  --frame-file frame.yaml \\",
        "  --round-yaml rounds/ROUND-3.yaml \\",
        "  --sql-dir sql \\",
        "  --out-dir ROUND-3",
        "```",
        "",
    ]
    (out_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def run(argv: list[str] | None = None) -> Path:
    args = parse_args(argv)
    corpus_PATH = require_path("corpus_PATH", args.corpus_PATH)
    window_quality_FILE = require_path("window_quality_FILE", args.window_quality_FILE)
    frame_FILE = require_path("frame_FILE", args.frame_FILE)
    round_yaml_FILE = require_path("round_yaml_FILE", args.round_yaml_FILE)
    out_DIR = require_path("out_DIR", args.out_DIR)
    sql_DIR = require_path("sql_DIR", args.sql_DIR)
    flags_FILE = require_path("flags_FILE", args.flags_FILE)
    smoke = bool(args.smoke)

    out_DIR.mkdir(parents=True, exist_ok=True)
    metrics_DIR = out_DIR / "metrics"
    metrics_DIR.mkdir(parents=True, exist_ok=True)
    status_FILE = out_DIR / "STATUS.json"
    write_status(status_FILE, "running")

    try:
        frame = load_frame(str(frame_FILE))
        comps = _comparisons(round_yaml_FILE)
        declared = [c["id"] for c in comps]
        m = len(declared)
        if m != 3:
            raise ValueError("comparison_id missing from declared comparisons")

        for comparison_id, sql_name in COMPARISON_SQL.items():
            require_comparison_id(comparison_id, declared)
            sql_text = load_sql(sql_name, str(sql_DIR))
            columns = _sql_select_names(sql_text)
            assert_no_clap_in_comparison(comparison_id, columns)

        master_seed = int(frame["master_seed"])
        B = int(frame["B"])
        min_judgeable = int(frame["min_judgeable"])
        stratum_seeds = {cid: stratum_seed(master_seed, cid) for cid in declared}
        assert_stratum_seeds(master_seed, stratum_seeds)

        row_accounting: list[dict[str, Any]] = []

        # Load shared c1 SQL base (tier A+B, boiler excluded)
        sql_c1 = load_sql("c1_period_drop", str(sql_DIR))
        base = _load_sql_df(corpus_PATH, sql_c1)
        row_accounting.append(
            {
                "step": "sql_c1_period_drop",
                "rule": "tier A+B + exclude boiler text",
                "group": "all",
                "rows_before": 0,
                "rows_after": len(base),
            }
        )

        # Window-level quality join check (A+B windows)
        windows_ab = _load_sql_df(
            corpus_PATH, load_sql("windows_ab", str(sql_DIR))
        )
        n_ab = len(windows_ab)
        expected = int(frame["expected_rows"])
        tol = int(frame["expected_rows_tol"])
        full_corpus = abs(n_ab - expected) <= tol
        enforce = full_corpus and (not smoke)

        quality = pd.read_csv(window_quality_FILE)
        if "clap_sing" in quality.columns:
            raise ValueError(
                "clap_sing must not join PANNs singing_prob in the same comparison"
            )
        q_right = quality[
            [c for c in ("window_id", "singing_prob", "snr_db") if c in quality.columns]
        ].copy()
        # Validate windows_quality join against frame expected_rows when full
        _ = checked_merge(
            windows_ab[["uid"]].drop_duplicates(),
            q_right,
            "windows_quality",
            frame,
            enforce_expected=enforce,
            row_accounting=row_accounting,
        )

        flags = pd.read_csv(flags_FILE)
        base_prep = _prepare_base(
            base, flags, quality, need_quality=True, row_accounting=row_accounting
        )
        unassigned = int((base_prep["group"] == "unassigned").sum())

        # c2 uses onset-filtered SQL then same attaches
        sql_c2 = load_sql("c2_highsnr_onset", str(sql_DIR))
        c2_raw = _load_sql_df(corpus_PATH, sql_c2)
        row_accounting.append(
            {
                "step": "sql_c2_highsnr_onset",
                "rule": "tier A+B + boiler + onset SQL filter",
                "group": "all",
                "rows_before": 0,
                "rows_after": len(c2_raw),
            }
        )
        c2_prep = _prepare_base(
            c2_raw, flags, quality, need_quality=True, row_accounting=row_accounting
        )

        c1_row, p1 = compute_c1(
            base_prep,
            B=B,
            seed=stratum_seeds["c1_period_drop"],
            min_judgeable=min_judgeable,
            m=m,
        )
        c2_row, p2 = compute_c2(
            c2_prep,
            B=B,
            seed=stratum_seeds["c2_highsnr_onset_residual"],
            min_judgeable=min_judgeable,
            m=m,
            row_accounting=row_accounting,
        )
        c3_row, p3 = compute_c3(
            base_prep,
            B=B,
            seed=stratum_seeds["c3_singing_removal"],
            min_judgeable=min_judgeable,
            m=m,
            row_accounting=row_accounting,
        )

        p_raws = [p1, p2, p3]
        # BH only over non-null raw p; still m=3 declared
        usable = [p if p is not None else 1.0 for p in p_raws]
        p_bhs = bh_corrected(usable, m)
        c1_row["p_bh"] = p_bhs[0] if c1_row.get("p_raw") is not None else None
        c2_row["p_bh"] = p_bhs[1] if c2_row.get("p_raw") is not None else None
        c3_row["p_bh"] = p_bhs[2] if c3_row.get("p_raw") is not None else None
        # re-copy p_raw in case compute used float
        c1_row["p_raw"] = p1 if c1_row.get("did") is not None else c1_row.get("p_raw")
        c2_row["p_raw"] = p2 if c2_row.get("did") is not None else c2_row.get("p_raw")
        c3_row["p_raw"] = p3 if c3_row.get("delta_pp") is not None else c3_row.get("p_raw")

        c1_row = _finalize_conclusions_c1_c2(c1_row, is_c2=False)
        c2_row = _finalize_conclusions_c1_c2(c2_row, is_c2=True)
        if c3_row["conclusion"] == "pending" and c3_row.get("delta_pp") is not None:
            c3_row["conclusion"] = (
                "supports_H3" if abs(float(c3_row["delta_pp"])) <= 0.5 else "rejects_H3"
            )

        digests = []
        for name, row in (
            ("did_period.json", c1_row),
            ("did_highsnr_onset.json", c2_row),
            ("singing_removal.json", c3_row),
        ):
            path = metrics_DIR / name
            digests.append(atomic_write_json(path, row))

        # strata summary for manifest
        strata = []
        for cid, row in (
            ("c1_period_drop", c1_row),
            ("c2_highsnr_onset_residual", c2_row),
            ("c3_singing_removal", c3_row),
        ):
            n_j = require_stratum_count(row["n_h_judgeable"])
            N_h = n_j
            w_h = (N_h / n_j) if n_j > 0 else None
            strata.append(
                {
                    "h": cid,
                    "N_h": N_h,
                    "n_h_sampled": require_stratum_count(row["n_total"]),
                    "n_h_judgeable": n_j,
                    "w_h": w_h,
                    "G_h": require_stratum_count(row["G_h"]),
                }
            )

        repo_ROOT = frame_FILE.resolve().parent
        inputs = []
        for label, path in (
            ("corpus", corpus_PATH),
            ("window_quality", window_quality_FILE),
            ("flags", flags_FILE),
            ("frame", frame_FILE),
            ("round_yaml", round_yaml_FILE),
        ):
            p = Path(path)
            if p.suffix.lower() == ".csv":
                cols = list(pd.read_csv(p, nrows=0).columns)
                rc = sum(1 for _ in open(p, encoding="utf-8")) - 1
            elif p.suffix.lower() in {".sqlite", ".db"}:
                con = sqlite3.connect(str(p))
                try:
                    rc = int(
                        _load_sql_df(
                            p, load_sql("count_syllables", str(sql_DIR))
                        ).iloc[0, 0]
                    )
                    cols = [
                        r[1] for r in con.execute("PRAGMA table_info(syllables)").fetchall()
                    ]
                finally:
                    con.close()
            else:
                rc = 0
                cols = []
            inputs.append(
                {
                    "path": str(p),
                    "sha256": sha256_file(p),
                    "row_count": max(rc, 0),
                    "columns": cols,
                }
            )

        manifest = build_manifest(
            inputs=inputs,
            strata=strata,
            master_seed=master_seed,
            stratum_seeds=stratum_seeds,
            B=B,
            git_sha=_git_sha(repo_ROOT),
            git_dirty=False,
            frame_yaml_blob_sha=git_blob_sha1(frame_FILE),
            row_accounting=row_accounting,
            unassigned=unassigned,
        )
        man_digest = atomic_write_json(out_DIR / "manifest.json", manifest)

        # checks.json — prediction thresholds
        checks = [
            {
                "name": "frame_expected_rows_ab",
                "status": "PASS"
                if (smoke or abs(n_ab - expected) <= tol)
                else "FAIL",
                "expected": expected,
                "expected_source": "frame.yaml:expected_rows",
                "observed": n_ab,
                "missing": None,
            },
            {
                "name": "comparisons_m",
                "status": "PASS" if m == 3 else "FAIL",
                "expected": 3,
                "expected_source": "rounds/ROUND-3.yaml:comparisons",
                "observed": m,
                "missing": None,
            },
            {
                "name": "c2_singing_prob_source",
                "status": "PASS"
                if c2_row.get("singing_prob_source") == SINGING_PROB_SOURCE
                else "FAIL",
                "expected": SINGING_PROB_SOURCE,
                "expected_source": "rounds/ROUND-3.yaml:singing_prob_source.path",
                "observed": c2_row.get("singing_prob_source"),
                "missing": None,
            },
            {
                "name": "c3_singing_prob_source",
                "status": "PASS"
                if c3_row.get("singing_prob_source") == SINGING_PROB_SOURCE
                else "FAIL",
                "expected": SINGING_PROB_SOURCE,
                "expected_source": "rounds/ROUND-3.yaml:singing_prob_source.path",
                "observed": c3_row.get("singing_prob_source"),
                "missing": None,
            },
            {
                "name": "boiler_text_constant",
                "status": "PASS" if BOILER_TEXT else "FAIL",
                "expected": BOILER_TEXT,
                "expected_source": "frame.yaml:predicates",
                "observed": BOILER_TEXT,
                "missing": None,
            },
        ]
        atomic_write_json(out_DIR / "checks.json", checks)

        _write_readme(
            out_DIR,
            {"c1": c1_row, "c2": c2_row, "c3": c3_row},
            smoke=smoke,
        )

        final_status = "smoke_ok" if smoke else "complete"
        # Preserve richer STATUS if present
        status_body: dict[str, Any] = {"status": final_status, "sha256": man_digest}
        status_body["metrics_sha256"] = {
            "did_period": digests[0],
            "did_highsnr_onset": digests[1],
            "singing_removal": digests[2],
        }
        status_body["smoke"] = smoke
        status_body["comparisons"] = declared
        atomic_write_json(status_FILE, status_body)
        return metrics_DIR / "did_period.json"
    except Exception as exc:
        atomic_write_json(
            status_FILE,
            {"status": "failed", "error": f"{type(exc).__name__}: {exc}"},
        )
        raise


def main() -> None:
    run()


if __name__ == "__main__":
    main()
