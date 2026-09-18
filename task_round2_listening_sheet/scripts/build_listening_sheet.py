#!/usr/bin/env python3
"""ROUND-2 stage-2: stratified listening sheet for human annotation.

One entrypoint for (a) clap×PANNs quartile-cross sampling and
(b) --summarize-labels of singing_rate / recitation_or_mixed_rate JSON.

Quartiles are always computed on the full joinable set
(clap_ok=1 ∩ quality ∩ window flags ∩ var) before sampling.
--limit only caps the sample size (and scales n_film / n_contemporary).

Does not record analysis conclusions. No audio / sqlite / weights.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_N_TOTAL = 200
DEFAULT_N_FILM = 160
DEFAULT_N_CONTEMPORARY = 40
DEFAULT_SEED = 20260918

SHEET_COLUMNS = [
    "window_id",
    "video_id",
    "film_flag",
    "clap_sing",
    "singing_prob",
    "var_db",
    "stratum",
    "human_label",
    "annotator_note",
    "forced_flag_sing",
]
HUMAN_LABELS = (
    "dialogue",
    "singing",
    "recitation",
    "mixed",
    "transcription_error",
    "unset",
)
STRATA = [
    "both_high",
    "both_low",
    "panns_high_only",
    "clap_high_only",
    "mid",
]
MANIFEST_REQUIRED = (
    "seed",
    "n_total",
    "n_film",
    "n_contemporary",
    "q1_clap",
    "q3_clap",
    "q1_panns",
    "q3_panns",
    "stratum_quotas",
    "window_ids",
    "forced_flag_sing_ids",
    "forced_in_quota",
)
CLAP_REQUIRED = ("window_id", "clap_sing", "clap_ok")
QUALITY_REQUIRED = ("window_id", "singing_prob", "flag_sing")
VAR_REQUIRED = ("window_id", "var_db")
FLAGS_REQUIRED = ("window_id", "video_id", "film_flag")
QUADRANT_KEYS = ("singing_rate_both_high", "singing_rate_both_low")
GAP_KEYS = (
    "singing_rate_panns_high_only",
    "singing_rate_clap_high_only",
)
FILM_METRIC_KEYS = (
    "recitation_or_mixed_rate",
    "contemporary_recitation_or_mixed_rate",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return float(format(x, ".12g"))
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2) + "\n", encoding="utf-8")


def _require_columns(df: pd.DataFrame, required: tuple[str, ...], label: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"{label} missing columns: {missing}")


def _check_unique_window_id(df: pd.DataFrame, label: str) -> None:
    if df["window_id"].duplicated().any():
        dups = df.loc[df["window_id"].duplicated(), "window_id"].tolist()
        raise SystemExit(f"duplicate window_id in {label}: {dups[:5]}")


def load_clap_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise SystemExit(f"--clap-csv not found: {path}")
    df = pd.read_csv(path)
    _require_columns(df, CLAP_REQUIRED, "clap CSV")
    out = df.loc[:, ["window_id", "clap_sing", "clap_ok"]].copy()
    out["window_id"] = out["window_id"].astype(str)
    out["clap_ok"] = pd.to_numeric(out["clap_ok"], errors="coerce").fillna(0).astype(int)
    out["clap_sing"] = pd.to_numeric(out["clap_sing"], errors="coerce")
    _check_unique_window_id(out, "clap CSV")
    return out


def load_quality_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise SystemExit(f"--quality-csv not found: {path}")
    df = pd.read_csv(path)
    missing = [c for c in QUALITY_REQUIRED if c not in df.columns]
    if missing:
        raise SystemExit(
            "--quality-csv MUST be the with_flags file "
            f"(columns {list(QUALITY_REQUIRED)}); missing {missing}. "
            "Do not pass bare window_quality.csv."
        )
    out = df.loc[:, list(QUALITY_REQUIRED)].copy()
    out["window_id"] = out["window_id"].astype(str)
    out["singing_prob"] = pd.to_numeric(out["singing_prob"], errors="coerce")
    out["flag_sing"] = (
        pd.to_numeric(out["flag_sing"], errors="coerce").fillna(0).astype(int)
    )
    _check_unique_window_id(out, "quality CSV")
    return out


def load_var_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise SystemExit(f"--var-csv not found: {path}")
    df = pd.read_csv(path)
    _require_columns(df, VAR_REQUIRED, "var CSV")
    out = df.loc[:, ["window_id", "var_db"]].copy()
    out["window_id"] = out["window_id"].astype(str)
    out["var_db"] = pd.to_numeric(out["var_db"], errors="coerce")
    _check_unique_window_id(out, "var CSV")
    return out


def load_flags_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise SystemExit(f"--flags-csv not found: {path}")
    df = pd.read_csv(path)
    if "window_id" not in df.columns:
        raise SystemExit(
            "--flags-csv MUST be window-level window_multilabel_flags.csv "
            "(columns window_id, video_id, film_flag). "
            "Do not pass video-level video_multilabel_flags.csv."
        )
    _require_columns(df, FLAGS_REQUIRED, "flags CSV")
    out = df.loc[:, list(FLAGS_REQUIRED)].copy()
    out["window_id"] = out["window_id"].astype(str)
    out["video_id"] = out["video_id"].astype(str)
    out["film_flag"] = (
        pd.to_numeric(out["film_flag"], errors="coerce").fillna(0).astype(int)
    )
    _check_unique_window_id(out, "flags CSV")
    return out


def joinable_set(
    clap: pd.DataFrame,
    quality: pd.DataFrame,
    var: pd.DataFrame,
    flags: pd.DataFrame,
) -> pd.DataFrame:
    """Inner-join clap_ok=1 ∩ quality ∩ window flags ∩ var; drop incomplete scores."""
    ok = clap.loc[clap["clap_ok"] == 1, ["window_id", "clap_sing"]].copy()
    merged = (
        ok.merge(quality, on="window_id", how="inner")
        .merge(var, on="window_id", how="inner")
        .merge(flags, on="window_id", how="inner")
    )
    merged = merged.dropna(subset=["clap_sing", "singing_prob", "var_db", "film_flag"])
    return merged.reset_index(drop=True)


def quartile_cuts(joinable: pd.DataFrame) -> dict[str, float]:
    if joinable.empty:
        raise SystemExit("joinable set is empty; cannot compute quartiles")
    clap = joinable["clap_sing"].to_numpy(dtype=float)
    panns = joinable["singing_prob"].to_numpy(dtype=float)
    return {
        "q1_clap": float(np.quantile(clap, 0.25, method="linear")),
        "q3_clap": float(np.quantile(clap, 0.75, method="linear")),
        "q1_panns": float(np.quantile(panns, 0.25, method="linear")),
        "q3_panns": float(np.quantile(panns, 0.75, method="linear")),
    }


def assign_stratum_row(
    clap_sing: float,
    singing_prob: float,
    q1_clap: float,
    q3_clap: float,
    q1_panns: float,
    q3_panns: float,
) -> str:
    if clap_sing >= q3_clap and singing_prob >= q3_panns:
        return "both_high"
    if clap_sing <= q1_clap and singing_prob <= q1_panns:
        return "both_low"
    if singing_prob >= q3_panns and clap_sing < q3_clap:
        return "panns_high_only"
    if clap_sing >= q3_clap and singing_prob < q3_panns:
        return "clap_high_only"
    return "mid"


def assign_strata(joinable: pd.DataFrame, cuts: dict[str, float]) -> pd.DataFrame:
    out = joinable.copy()
    out["stratum"] = [
        assign_stratum_row(
            float(clap),
            float(panns),
            cuts["q1_clap"],
            cuts["q3_clap"],
            cuts["q1_panns"],
            cuts["q3_panns"],
        )
        for clap, panns in zip(out["clap_sing"].tolist(), out["singing_prob"].tolist())
    ]
    return out


def equal_quotas(n: int) -> dict[str, int]:
    """Equal split across the five quartile-cross strata; remainder to corners first."""
    n = max(0, int(n))
    base, rem = divmod(n, len(STRATA))
    quotas = {s: base for s in STRATA}
    for i in range(rem):
        quotas[STRATA[i]] += 1
    return quotas


def scale_group_targets(
    n_total: int,
    n_film: int,
    n_contemporary: int,
    limit: int | None,
) -> tuple[int, int, int]:
    if n_film < 0 or n_contemporary < 0 or n_total < 0:
        raise SystemExit("n_total / n_film / n_contemporary must be >= 0")
    if n_film + n_contemporary != n_total:
        raise SystemExit(
            f"n_film ({n_film}) + n_contemporary ({n_contemporary}) "
            f"must equal n_total ({n_total})"
        )
    if limit is None:
        return n_total, n_film, n_contemporary
    if limit < 1:
        raise SystemExit("--limit must be >= 1")
    if limit >= n_total:
        return n_total, n_film, n_contemporary
    n_film_s = int(round(n_film * limit / n_total))
    n_film_s = min(max(n_film_s, 0), limit)
    n_contemp_s = limit - n_film_s
    return limit, n_film_s, n_contemp_s


def _shuffle_ids(series: pd.Series, rng: np.random.Generator) -> list[str]:
    ids = np.array(sorted(series.astype(str).tolist()), dtype=object)
    rng.shuffle(ids)
    return ids.tolist()


def _fit_need_to_budget(need: dict[str, int], budget: int) -> dict[str, int]:
    need = {s: max(0, int(need[s])) for s in STRATA}
    total = sum(need.values())
    budget = max(0, int(budget))
    if total < budget:
        extra = budget - total
        i = 0
        while extra > 0:
            need[STRATA[i % len(STRATA)]] += 1
            extra -= 1
            i += 1
        return need
    if total > budget:
        over = total - budget
        for s in reversed(STRATA):
            take = min(over, need[s])
            need[s] -= take
            over -= take
            if over == 0:
                break
    return need


def sample_group(
    pool: pd.DataFrame,
    n_target: int,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Sample one film_flag group. All flag_sing=1 are forced in (rule A)."""
    empty = pool.iloc[0:0]
    if pool.empty:
        return empty, equal_quotas(0)

    forced = pool.loc[pool["flag_sing"] == 1].copy()
    rest = pool.loc[pool["flag_sing"] != 1].copy()
    n_forced = int(len(forced))
    # Rule A: keep every forced row even if that exceeds n_target.
    n_eff = min(max(int(n_target), n_forced), int(len(pool)))
    quotas = equal_quotas(n_eff)
    n_remain = n_eff - n_forced

    forced_counts = (
        forced["stratum"].value_counts().to_dict() if n_forced else {}
    )
    need = {
        s: max(0, quotas[s] - int(forced_counts.get(s, 0))) for s in STRATA
    }
    need = _fit_need_to_budget(need, n_remain)

    leftover = rest
    picked_ids: list[str] = []
    for s in STRATA:
        cand = leftover.loc[leftover["stratum"] == s]
        take_n = min(need[s], len(cand))
        if take_n <= 0:
            continue
        ids = _shuffle_ids(cand["window_id"], rng)[:take_n]
        picked_ids.extend(ids)
        leftover = leftover.loc[~leftover["window_id"].isin(ids)]

    shortfall = n_remain - len(picked_ids)
    if shortfall > 0 and len(leftover):
        for s in STRATA:
            if shortfall <= 0:
                break
            cand = leftover.loc[leftover["stratum"] == s]
            take_n = min(shortfall, len(cand))
            if take_n <= 0:
                continue
            ids = _shuffle_ids(cand["window_id"], rng)[:take_n]
            picked_ids.extend(ids)
            leftover = leftover.loc[~leftover["window_id"].isin(ids)]
            shortfall -= take_n
        if shortfall > 0 and len(leftover):
            ids = _shuffle_ids(leftover["window_id"], rng)[:shortfall]
            picked_ids.extend(ids)

    rest_picked = rest.loc[rest["window_id"].isin(picked_ids)].copy()
    out = pd.concat([forced, rest_picked], ignore_index=True)
    out = out.drop_duplicates(subset=["window_id"])
    return out, quotas


def sample_sheet(
    labeled: pd.DataFrame,
    n_film: int,
    n_contemporary: int,
    seed: int,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    rng = np.random.default_rng(seed)
    film_pool = labeled.loc[labeled["film_flag"] == 1]
    contemp_pool = labeled.loc[labeled["film_flag"] != 1]
    n_film_eff = min(int(n_film), int(len(film_pool)))
    n_contemp_eff = min(int(n_contemporary), int(len(contemp_pool)))
    # Forced rows still enter even if they exceed the (already pool-capped) target.
    n_film_forced = int((film_pool["flag_sing"] == 1).sum())
    n_contemp_forced = int((contemp_pool["flag_sing"] == 1).sum())
    n_film_eff = max(n_film_eff, n_film_forced)
    n_contemp_eff = max(n_contemp_eff, n_contemp_forced)

    film_rows, film_quotas = sample_group(film_pool, n_film_eff, rng)
    contemp_rows, contemp_quotas = sample_group(contemp_pool, n_contemp_eff, rng)
    sheet = pd.concat([film_rows, contemp_rows], ignore_index=True)
    quotas = {"film": film_quotas, "contemporary": contemp_quotas}
    return sheet, quotas


def format_sheet(sampled: pd.DataFrame) -> pd.DataFrame:
    out = sampled.copy()
    out["window_id"] = out["window_id"].astype(str)
    out["video_id"] = out["video_id"].astype(str)
    out["film_flag"] = out["film_flag"].astype(int)
    out["forced_flag_sing"] = (out["flag_sing"].astype(int) == 1).astype(int)
    out["human_label"] = "unset"
    out["annotator_note"] = ""
    out = out.loc[:, SHEET_COLUMNS].sort_values("window_id").reset_index(drop=True)
    return out


def write_sheet_csv(path: Path, sheet: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.loc[:, SHEET_COLUMNS].to_csv(path, index=False)


def build_manifest(
    *,
    seed: int,
    n_total: int,
    n_film: int,
    n_contemporary: int,
    cuts: dict[str, float],
    quotas: dict[str, dict[str, int]],
    sheet: pd.DataFrame,
    joinable: pd.DataFrame,
    limit: int | None,
    n_total_request: int,
    n_film_request: int,
    n_contemporary_request: int,
) -> dict[str, Any]:
    forced_ids = sorted(
        joinable.loc[joinable["flag_sing"] == 1, "window_id"].astype(str).tolist()
    )
    window_ids = sheet["window_id"].astype(str).tolist()
    actual_film = int((sheet["film_flag"] == 1).sum())
    actual_contemp = int((sheet["film_flag"] != 1).sum())
    stratum_counts: dict[str, dict[str, int]] = {"film": {}, "contemporary": {}}
    for key, mask in (
        ("film", sheet["film_flag"] == 1),
        ("contemporary", sheet["film_flag"] != 1),
    ):
        sub = sheet.loc[mask]
        for s in STRATA:
            stratum_counts[key][s] = int((sub["stratum"] == s).sum())
    return {
        "seed": int(seed),
        "n_total": int(n_total_request),
        "n_film": int(n_film_request),
        "n_contemporary": int(n_contemporary_request),
        "n_total_target": int(n_total),
        "n_film_target": int(n_film),
        "n_contemporary_target": int(n_contemporary),
        "n_total_actual": int(len(sheet)),
        "n_film_actual": actual_film,
        "n_contemporary_actual": actual_contemp,
        "n_joinable": int(len(joinable)),
        "limit": limit,
        "q1_clap": cuts["q1_clap"],
        "q3_clap": cuts["q3_clap"],
        "q1_panns": cuts["q1_panns"],
        "q3_panns": cuts["q3_panns"],
        "stratum_quotas": quotas,
        "stratum_counts_actual": stratum_counts,
        "window_ids": window_ids,
        "forced_flag_sing_ids": forced_ids,
        "forced_in_quota": True,
    }


def validate_sheet_smoke(sheet: pd.DataFrame) -> bool:
    if sheet.empty:
        return False
    if list(sheet.columns) != SHEET_COLUMNS:
        return False
    labels = sheet["human_label"].astype(str)
    return bool((labels == "unset").all())


def write_status(
    path: Path,
    *,
    smoke_ok: bool,
    extra: dict[str, Any] | None = None,
) -> None:
    status = {
        "task": "round2_listening_sheet",
        "smoke_ok": bool(smoke_ok),
        "updated_at": _now_iso(),
    }
    if extra:
        status.update(extra)
    write_json(path, status)


def build_listening_sheet(
    clap_csv: Path,
    quality_csv: Path,
    var_csv: Path,
    flags_csv: Path,
    out_dir: Path,
    n_total: int = DEFAULT_N_TOTAL,
    n_film: int = DEFAULT_N_FILM,
    n_contemporary: int = DEFAULT_N_CONTEMPORARY,
    seed: int = DEFAULT_SEED,
    limit: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    clap = load_clap_csv(clap_csv)
    quality = load_quality_csv(quality_csv)
    var = load_var_csv(var_csv)
    flags = load_flags_csv(flags_csv)
    joinable = joinable_set(clap, quality, var, flags)
    if joinable.empty:
        raise SystemExit("no joinable windows (clap_ok=1 ∩ quality ∩ flags ∩ var)")

    # Quartiles on the FULL joinable set, before any sample-size cap.
    cuts = quartile_cuts(joinable)
    labeled = assign_strata(joinable, cuts)

    n_total_req, n_film_req, n_contemp_req = n_total, n_film, n_contemporary
    n_total_t, n_film_t, n_contemp_t = scale_group_targets(
        n_total, n_film, n_contemporary, limit
    )
    sampled, quotas = sample_sheet(labeled, n_film_t, n_contemp_t, seed)
    sheet = format_sheet(sampled)
    manifest = build_manifest(
        seed=seed,
        n_total=n_total_t,
        n_film=n_film_t,
        n_contemporary=n_contemp_t,
        cuts=cuts,
        quotas=quotas,
        sheet=sheet,
        joinable=labeled,
        limit=limit,
        n_total_request=n_total_req,
        n_film_request=n_film_req,
        n_contemporary_request=n_contemp_req,
    )
    missing = [k for k in MANIFEST_REQUIRED if k not in manifest]
    if missing:
        raise SystemExit(f"manifest missing required keys: {missing}")
    if manifest["forced_in_quota"] is not True:
        raise SystemExit("forced_in_quota must be true (rule A)")

    out_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = out_dir / "listening_sheet.csv"
    manifest_path = out_dir / "sample_manifest.json"
    status_path = out_dir / "STATUS.json"
    write_sheet_csv(sheet_path, sheet)
    write_json(manifest_path, manifest)
    smoke_ok = validate_sheet_smoke(sheet)
    write_status(
        status_path,
        smoke_ok=smoke_ok,
        extra={
            "n_joinable": int(len(joinable)),
            "n_sheet": int(len(sheet)),
            "n_film_actual": manifest["n_film_actual"],
            "n_contemporary_actual": manifest["n_contemporary_actual"],
            "n_forced_flag_sing": len(manifest["forced_flag_sing_ids"]),
            "limit": limit,
            "seed": int(seed),
            "sheet": str(sheet_path),
            "manifest": str(manifest_path),
            "clap_csv": str(clap_csv),
            "quality_csv": str(quality_csv),
            "var_csv": str(var_csv),
            "flags_csv": str(flags_csv),
        },
    )
    print(f"Wrote {sheet_path} n={len(sheet)}", flush=True)
    print(f"Wrote {manifest_path}", flush=True)
    print(f"Wrote {status_path} smoke_ok={smoke_ok}", flush=True)
    return sheet, manifest, cuts


def _labeled_subset(sheet: pd.DataFrame, mask: pd.Series) -> pd.Series:
    sub = sheet.loc[mask, "human_label"].astype(str)
    return sub.loc[sub != "unset"]


def _mean_equals(labels: pd.Series, value: str) -> float | None:
    if labels.empty:
        return None
    return float((labels == value).mean())


def _mean_in(labels: pd.Series, values: set[str]) -> float | None:
    if labels.empty:
        return None
    return float(labels.isin(values).mean())


def summarize_labels(sheet_path: Path, manifest_path: Path, out_dir: Path) -> dict[str, dict]:
    if not sheet_path.is_file():
        raise SystemExit(f"--sheet not found: {sheet_path}")
    if not manifest_path.is_file():
        raise SystemExit(f"--manifest not found: {manifest_path}")
    sheet = pd.read_csv(sheet_path)
    missing = [c for c in ("stratum", "human_label", "film_flag") if c not in sheet.columns]
    if missing:
        raise SystemExit(f"sheet missing columns: {missing}")
    sheet["human_label"] = sheet["human_label"].astype(str)
    sheet["stratum"] = sheet["stratum"].astype(str)
    sheet["film_flag"] = pd.to_numeric(sheet["film_flag"], errors="coerce").fillna(0).astype(int)

    unknown = sorted(
        set(sheet["human_label"].unique()) - set(HUMAN_LABELS)
    )
    if unknown:
        raise SystemExit(f"unknown human_label values: {unknown}")

    by_stratum_labels = {
        s: _labeled_subset(sheet, sheet["stratum"] == s) for s in STRATA
    }
    quadrant = {
        "singing_rate_both_high": _mean_equals(
            by_stratum_labels["both_high"], "singing"
        ),
        "singing_rate_both_low": _mean_equals(
            by_stratum_labels["both_low"], "singing"
        ),
        "n_labeled_both_high": int(len(by_stratum_labels["both_high"])),
        "n_labeled_both_low": int(len(by_stratum_labels["both_low"])),
    }
    gap = {
        "singing_rate_panns_high_only": _mean_equals(
            by_stratum_labels["panns_high_only"], "singing"
        ),
        "singing_rate_clap_high_only": _mean_equals(
            by_stratum_labels["clap_high_only"], "singing"
        ),
        "n_labeled_panns_high_only": int(len(by_stratum_labels["panns_high_only"])),
        "n_labeled_clap_high_only": int(len(by_stratum_labels["clap_high_only"])),
    }
    film_lab = _labeled_subset(sheet, sheet["film_flag"] == 1)
    contemp_lab = _labeled_subset(sheet, sheet["film_flag"] != 1)
    rec_mixed = {"recitation", "mixed"}
    by_film = {
        "recitation_or_mixed_rate": _mean_in(film_lab, rec_mixed),
        "contemporary_recitation_or_mixed_rate": _mean_in(contemp_lab, rec_mixed),
        "n_labeled_film": int(len(film_lab)),
        "n_labeled_contemporary": int(len(contemp_lab)),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "label_by_quadrant": out_dir / "label_by_quadrant.json",
        "single_track_gap": out_dir / "single_track_gap.json",
        "label_by_film": out_dir / "label_by_film.json",
    }
    write_json(paths["label_by_quadrant"], quadrant)
    write_json(paths["single_track_gap"], gap)
    write_json(paths["label_by_film"], by_film)
    for p in paths.values():
        print(f"Wrote {p}", flush=True)
    return {"label_by_quadrant": quadrant, "single_track_gap": gap, "label_by_film": by_film}


# ---------------------------------------------------------------------------
# Fixtures / self-test (no audio)
# ---------------------------------------------------------------------------


def _fixture_rows(n: int = 40) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(n):
        vid = f"v{i // 4:02d}"
        wid = f"{vid}_{i % 4:03d}"
        rows.append(
            {
                "window_id": wid,
                "video_id": vid,
                "clap_sing": round(i / max(n - 1, 1), 6),
                "singing_prob": round(((i * 7) % n) / max(n - 1, 1), 6),
                "var_db": round(5.0 + 0.3 * i, 4),
                "film_flag": 1 if i < int(round(n * 0.8)) else 0,
                "flag_sing": 1 if i in (5, 20, n - 5) else 0,
                "clap_ok": 1,
            }
        )
    return rows


def write_fixture_csvs(dir_path: Path, rows: list[dict[str, Any]] | None = None) -> dict[str, Path]:
    dir_path.mkdir(parents=True, exist_ok=True)
    rows = list(rows if rows is not None else _fixture_rows())
    extra_fail = {
        "window_id": "w_fail",
        "video_id": "wfail",
        "clap_sing": "",
        "singing_prob": 0.10,
        "var_db": 1.0,
        "film_flag": 0,
        "flag_sing": 0,
        "clap_ok": 0,
    }
    extra_orphan_clap = {
        "window_id": "w_orphan_clap",
        "video_id": "orphan",
        "clap_sing": 0.55,
        "singing_prob": "",
        "var_db": "",
        "film_flag": "",
        "flag_sing": "",
        "clap_ok": 1,
    }
    clap_path = dir_path / "clap_tiny.csv"
    quality_path = dir_path / "quality_with_flags_tiny.csv"
    var_path = dir_path / "var_tiny.csv"
    flags_path = dir_path / "window_flags_tiny.csv"
    video_flags_path = dir_path / "video_flags_tiny.csv"

    with clap_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["window_id", "clap_sing", "clap_speak", "clap_logit_diff", "clap_ok", "error"],
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "window_id": r["window_id"],
                    "clap_sing": r["clap_sing"],
                    "clap_speak": round(1.0 - float(r["clap_sing"]), 6),
                    "clap_logit_diff": round(float(r["clap_sing"]) - (1.0 - float(r["clap_sing"])), 6),
                    "clap_ok": r["clap_ok"],
                    "error": "",
                }
            )
        w.writerow(
            {
                "window_id": extra_fail["window_id"],
                "clap_sing": extra_fail["clap_sing"],
                "clap_speak": "",
                "clap_logit_diff": "",
                "clap_ok": 0,
                "error": "synthetic_error",
            }
        )
        w.writerow(
            {
                "window_id": extra_orphan_clap["window_id"],
                "clap_sing": extra_orphan_clap["clap_sing"],
                "clap_speak": 0.45,
                "clap_logit_diff": 0.10,
                "clap_ok": 1,
                "error": "",
            }
        )

    with quality_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["window_id", "singing_prob", "flag_sing"])
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "window_id": r["window_id"],
                    "singing_prob": r["singing_prob"],
                    "flag_sing": r["flag_sing"],
                }
            )
        w.writerow(
            {
                "window_id": extra_fail["window_id"],
                "singing_prob": extra_fail["singing_prob"],
                "flag_sing": extra_fail["flag_sing"],
            }
        )
        w.writerow(
            {
                "window_id": "w_quality_only",
                "singing_prob": 0.99,
                "flag_sing": 1,
            }
        )

    with var_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["window_id", "var_db", "demucs_ok"])
        w.writeheader()
        for r in rows:
            w.writerow({"window_id": r["window_id"], "var_db": r["var_db"], "demucs_ok": 1})
        w.writerow(
            {"window_id": extra_fail["window_id"], "var_db": extra_fail["var_db"], "demucs_ok": 1}
        )

    with flags_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["window_id", "video_id", "film_flag"])
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "window_id": r["window_id"],
                    "video_id": r["video_id"],
                    "film_flag": r["film_flag"],
                }
            )
        w.writerow(
            {
                "window_id": extra_fail["window_id"],
                "video_id": extra_fail["video_id"],
                "film_flag": extra_fail["film_flag"],
            }
        )

    with video_flags_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["video_id", "film_flag", "title"])
        w.writeheader()
        seen = set()
        for r in rows:
            if r["video_id"] in seen:
                continue
            seen.add(r["video_id"])
            w.writerow(
                {
                    "video_id": r["video_id"],
                    "film_flag": r["film_flag"],
                    "title": f"synthetic {r['video_id']}",
                }
            )

    return {
        "clap": clap_path,
        "quality": quality_path,
        "var": var_path,
        "flags": flags_path,
        "video_flags": video_flags_path,
    }


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"SELF-TEST FAILED: {msg}")


def _assert_close(a: Any, b: float, msg: str, tol: float = 1e-9) -> None:
    _assert(a is not None and abs(float(a) - b) < tol, f"{msg}: {a} vs {b}")


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="round2_sheet_selftest_") as tmp:
        tmp_path = Path(tmp)
        fx = write_fixture_csvs(tmp_path / "fixtures")
        out_dir = tmp_path / "out"
        sheet, manifest, cuts = build_listening_sheet(
            fx["clap"],
            fx["quality"],
            fx["var"],
            fx["flags"],
            out_dir,
            n_total=DEFAULT_N_TOTAL,
            n_film=DEFAULT_N_FILM,
            n_contemporary=DEFAULT_N_CONTEMPORARY,
            seed=DEFAULT_SEED,
            limit=50,
        )
        _assert(len(sheet) >= 1, "sheet must have >=1 row")
        _assert(list(sheet.columns) == SHEET_COLUMNS, f"columns={list(sheet.columns)}")
        _assert((sheet["human_label"] == "unset").all(), "human_label not all unset")
        _assert(manifest["forced_in_quota"] is True, "forced_in_quota")
        for key in MANIFEST_REQUIRED:
            _assert(key in manifest, f"manifest missing {key}")

        status = json.loads((out_dir / "STATUS.json").read_text(encoding="utf-8"))
        _assert(status.get("smoke_ok") is True, "smoke_ok")

        # Independent quartile recompute on full joinable set (not the --limit cap).
        clap = load_clap_csv(fx["clap"])
        quality = load_quality_csv(fx["quality"])
        var = load_var_csv(fx["var"])
        flags = load_flags_csv(fx["flags"])
        joinable = joinable_set(clap, quality, var, flags)
        indep = quartile_cuts(joinable)
        for k in ("q1_clap", "q3_clap", "q1_panns", "q3_panns"):
            _assert_close(cuts[k], indep[k], k)
            _assert_close(manifest[k], indep[k], f"manifest {k}")
        _assert(len(joinable) == 40, f"joinable={len(joinable)} expected 40")
        _assert("w_fail" not in set(joinable["window_id"]), "clap_ok=0 leaked")
        _assert("w_orphan_clap" not in set(joinable["window_id"]), "orphan clap leaked")
        _assert("w_quality_only" not in set(joinable["window_id"]), "quality-only leaked")

        labeled = assign_strata(joinable, indep)
        for rec in labeled.itertuples(index=False):
            expected = assign_stratum_row(
                float(rec.clap_sing),
                float(rec.singing_prob),
                indep["q1_clap"],
                indep["q3_clap"],
                indep["q1_panns"],
                indep["q3_panns"],
            )
            _assert(rec.stratum == expected, f"stratum {rec.window_id}")

        forced_joinable = sorted(
            labeled.loc[labeled["flag_sing"] == 1, "window_id"].astype(str).tolist()
        )
        _assert(forced_joinable == manifest["forced_flag_sing_ids"], "forced ids")
        sheet_ids = set(sheet["window_id"].astype(str))
        for wid in forced_joinable:
            _assert(wid in sheet_ids, f"forced {wid} missing from sheet")
            row = sheet.loc[sheet["window_id"] == wid].iloc[0]
            _assert(int(row["forced_flag_sing"]) == 1, f"forced_flag_sing for {wid}")

        # Video-level flags table must be rejected.
        raised = False
        try:
            load_flags_csv(fx["video_flags"])
        except SystemExit as exc:
            raised = True
            _assert("window-level" in str(exc) or "window_id" in str(exc), f"error text: {exc}")
        _assert(raised, "video-level flags CSV should be rejected")

        # Bare quality CSV (no flag_sing) must fail.
        bare = tmp_path / "window_quality.csv"
        with bare.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["window_id", "singing_prob", "music_prob"])
            w.writeheader()
            w.writerow({"window_id": "v00_000", "singing_prob": 0.1, "music_prob": 0.2})
        raised = False
        try:
            load_quality_csv(bare)
        except SystemExit as exc:
            raised = True
            _assert("with_flags" in str(exc), f"error text: {exc}")
        _assert(raised, "bare window_quality.csv should be rejected")

        # --summarize-labels with synthetic annotations; keys match ROUND predictions.
        labeled_sheet = sheet.copy()
        labels_cycle = ["singing", "dialogue", "recitation", "mixed", "transcription_error"]
        for i, idx in enumerate(labeled_sheet.index):
            if labeled_sheet.at[idx, "stratum"] == "both_high":
                labeled_sheet.at[idx, "human_label"] = "singing"
            elif labeled_sheet.at[idx, "stratum"] == "both_low":
                labeled_sheet.at[idx, "human_label"] = "dialogue"
            else:
                labeled_sheet.at[idx, "human_label"] = labels_cycle[i % len(labels_cycle)]
        lab_path = tmp_path / "labeled_sheet.csv"
        write_sheet_csv(lab_path, labeled_sheet)
        metrics_dir = tmp_path / "metrics"
        metrics = summarize_labels(lab_path, out_dir / "sample_manifest.json", metrics_dir)
        for k in QUADRANT_KEYS:
            _assert(k in metrics["label_by_quadrant"], k)
        for k in GAP_KEYS:
            _assert(k in metrics["single_track_gap"], k)
        for k in FILM_METRIC_KEYS:
            _assert(k in metrics["label_by_film"], k)
        _assert(
            metrics["label_by_quadrant"]["singing_rate_both_high"] == 1.0,
            "both_high singing_rate",
        )
        _assert(
            metrics["label_by_quadrant"]["singing_rate_both_low"] == 0.0,
            "both_low singing_rate",
        )
        # unset-only sheet → rates null, files still written
        unset_metrics = summarize_labels(
            out_dir / "listening_sheet.csv",
            out_dir / "sample_manifest.json",
            tmp_path / "metrics_unset",
        )
        _assert(unset_metrics["label_by_quadrant"]["singing_rate_both_high"] is None, "unset rate")

        # Same seed → identical window_ids
        out2 = tmp_path / "out2"
        _, manifest2, _ = build_listening_sheet(
            fx["clap"],
            fx["quality"],
            fx["var"],
            fx["flags"],
            out2,
            seed=DEFAULT_SEED,
            limit=50,
        )
        _assert(manifest["window_ids"] == manifest2["window_ids"], "seed not deterministic")

    print("SELF-TEST PASSED", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Build a stratified listening sheet (clap_sing × singing_prob "
            "quartile cross) or summarize human labels after annotation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/build_listening_sheet.py --help

  python scripts/build_listening_sheet.py \\
    --clap-csv fixtures/clap_tiny.csv \\
    --quality-csv fixtures/quality_with_flags_tiny.csv \\
    --var-csv fixtures/var_tiny.csv \\
    --flags-csv fixtures/window_flags_tiny.csv \\
    --out-dir /tmp/round2-smoke \\
    --n-total 200 --n-film 160 --n-contemporary 40 --seed 20260918 \\
    --limit 50

  python scripts/build_listening_sheet.py \\
    --clap-csv analysis/ROUND-1/window_clap_sing.csv \\
    --quality-csv analysis/task2_window_quality/window_quality_with_flags.csv \\
    --var-csv analysis/task_calib_demucs_var/window_var_db.csv \\
    --flags-csv analysis/task3_multilabel_flags/window_multilabel_flags.csv \\
    --out-dir analysis/ROUND-2 \\
    --n-total 200 --n-film 160 --n-contemporary 40 --seed 20260918

  python scripts/build_listening_sheet.py --summarize-labels \\
    --sheet analysis/ROUND-2/listening_sheet.csv \\
    --manifest analysis/ROUND-2/sample_manifest.json \\
    --out-dir analysis/ROUND-2/metrics

  python scripts/build_listening_sheet.py --self-test
""",
    )
    p.add_argument("--clap-csv", type=Path, help="ROUND-1 window_clap_sing.csv (clap_ok, clap_sing)")
    p.add_argument(
        "--quality-csv",
        type=Path,
        help="window_quality_with_flags.csv (singing_prob, flag_sing)",
    )
    p.add_argument("--var-csv", type=Path, help="window_var_db.csv (var_db)")
    p.add_argument(
        "--flags-csv",
        type=Path,
        help="window_multilabel_flags.csv (window-level film_flag; not the video table)",
    )
    p.add_argument("--out-dir", type=Path, help="Output directory for sheet / manifest / STATUS")
    p.add_argument("--n-total", type=int, default=DEFAULT_N_TOTAL)
    p.add_argument("--n-film", type=int, default=DEFAULT_N_FILM)
    p.add_argument("--n-contemporary", type=int, default=DEFAULT_N_CONTEMPORARY)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Smoke cap on sample size (quartiles still use the full joinable set)",
    )
    p.add_argument(
        "--summarize-labels",
        action="store_true",
        help="Write metrics JSON from an annotated listening_sheet.csv",
    )
    p.add_argument("--sheet", type=Path, help="listening_sheet.csv for --summarize-labels")
    p.add_argument("--manifest", type=Path, help="sample_manifest.json for --summarize-labels")
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Fixture checks for quartiles, rule A, CLI guards, summarize keys",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        run_self_test()
        return 0

    if args.summarize_labels:
        if not args.sheet or not args.manifest or not args.out_dir:
            raise SystemExit(
                "--summarize-labels requires --sheet, --manifest, and --out-dir"
            )
        summarize_labels(args.sheet, args.manifest, args.out_dir)
        return 0

    missing = [
        name
        for name, val in (
            ("--clap-csv", args.clap_csv),
            ("--quality-csv", args.quality_csv),
            ("--var-csv", args.var_csv),
            ("--flags-csv", args.flags_csv),
            ("--out-dir", args.out_dir),
        )
        if val is None
    ]
    if missing:
        raise SystemExit("sampling requires " + ", ".join(missing))

    build_listening_sheet(
        args.clap_csv,
        args.quality_csv,
        args.var_csv,
        args.flags_csv,
        args.out_dir,
        n_total=args.n_total,
        n_film=args.n_film,
        n_contemporary=args.n_contemporary,
        seed=args.seed,
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
