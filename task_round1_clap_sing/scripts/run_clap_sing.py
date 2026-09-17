#!/usr/bin/env python3
"""ROUND-1 stage-2: LAION-CLAP clap_sing vs PANNs singing_prob.

One entrypoint for (a) CPU CLAP inference on window FLAC files and
(b) --summarize of Spearman / flag_sing contrast JSON.

Heavy imports (torch / transformers) and Hub weight downloads happen only
when actually scoring audio — not on --help, --summarize, --dry-run, or
--self-test.

CSV columns: window_id,clap_sing,clap_speak,clap_logit_diff,clap_ok,error
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Summarize-only deps (root requirements). Do not import torch here.
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr

CLAP_MODEL_ID = "laion/larger_clap_music_and_speech"
PROMPTS = ("a person singing", "a person speaking")
CLAP_SR = 48000
CLAP_MAX_SECONDS = 10
CSV_FIELDS = [
    "window_id",
    "clap_sing",
    "clap_speak",
    "clap_logit_diff",
    "clap_ok",
    "error",
]
QUALITY_REQUIRED = ("window_id", "singing_prob", "flag_sing")
CORR_KEYS = ("spearman_clap_vs_panns", "n_paired")
CONTRAST_BASE_KEYS = (
    "median_clap_flag1",
    "median_clap_flag0",
    "n_flag1",
    "n_flag0",
)
MAX_WEIGHT_BYTES = 2 * 1024 ** 3
# Hub main (queried 2026-09-17): pytorch_model.bin 776_444_665 B + tokenizer/config.
DOCUMENTED_WEIGHT_BYTES = 779_815_910
HF_API_URL = (
    "https://huggingface.co/api/models/"
    f"{CLAP_MODEL_ID}?blobs=true"
)
BOOTSTRAP_N_DEFAULT = 2000
N_FLAG1_MW_MIN = 10


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
    path.write_text(
        json.dumps(json_safe(payload), indent=2) + "\n", encoding="utf-8"
    )


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
    if out["window_id"].duplicated().any():
        dups = out.loc[out["window_id"].duplicated(), "window_id"].tolist()
        raise SystemExit(f"duplicate window_id in quality CSV: {dups[:5]}")
    return out


def load_clap_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise SystemExit(f"clap CSV not found: {path}")
    df = pd.read_csv(path)
    missing = [c for c in CSV_FIELDS if c not in df.columns]
    if missing:
        raise SystemExit(f"clap CSV missing columns: {missing}")
    df = df.copy()
    df["window_id"] = df["window_id"].astype(str)
    df["clap_ok"] = pd.to_numeric(df["clap_ok"], errors="coerce").fillna(0).astype(int)
    for col in ("clap_sing", "clap_speak", "clap_logit_diff"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def pair_clap_quality(clap: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    ok = clap.loc[clap["clap_ok"] == 1].copy()
    merged = ok.merge(quality, on="window_id", how="inner")
    merged = merged.dropna(subset=["clap_sing", "singing_prob"])
    return merged.reset_index(drop=True)


def spearman_summary(paired: pd.DataFrame) -> dict:
    n_paired = int(len(paired))
    if n_paired < 2:
        return {"spearman_clap_vs_panns": None, "n_paired": n_paired}
    res = spearmanr(paired["clap_sing"].to_numpy(), paired["singing_prob"].to_numpy())
    rho = float(getattr(res, "statistic", res[0]))
    return {"spearman_clap_vs_panns": rho, "n_paired": n_paired}


def bootstrap_median_diff_ci(
    flag1: np.ndarray,
    flag0: np.ndarray,
    n_resamples: int,
    seed: int,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_resamples, dtype=np.float64)
    n1, n0 = len(flag1), len(flag0)
    for i in range(n_resamples):
        a = rng.choice(flag1, size=n1, replace=True)
        b = rng.choice(flag0, size=n0, replace=True)
        diffs[i] = float(np.median(a) - np.median(b))
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def flag_sing_contrast(
    paired: pd.DataFrame,
    n_resamples: int = BOOTSTRAP_N_DEFAULT,
    seed: int = 0,
) -> dict:
    flag1 = paired.loc[paired["flag_sing"] == 1, "clap_sing"].to_numpy(dtype=float)
    flag0 = paired.loc[paired["flag_sing"] == 0, "clap_sing"].to_numpy(dtype=float)
    n1, n0 = int(len(flag1)), int(len(flag0))
    out: dict[str, Any] = {
        "median_clap_flag1": float(np.median(flag1)) if n1 else None,
        "median_clap_flag0": float(np.median(flag0)) if n0 else None,
        "n_flag1": n1,
        "n_flag0": n0,
    }
    if n1 >= N_FLAG1_MW_MIN and n0 >= 1:
        out["mw_pvalue"] = float(
            mannwhitneyu(flag1, flag0, alternative="greater").pvalue
        )
        return out
    if n1 >= 1 and n0 >= 1:
        med1 = float(out["median_clap_flag1"])
        med0 = float(out["median_clap_flag0"])
        lo, hi = bootstrap_median_diff_ci(flag1, flag0, n_resamples, seed)
        out["median_diff"] = med1 - med0
        out["bootstrap_ci_low"] = lo
        out["bootstrap_ci_high"] = hi
        out["bootstrap_n"] = int(n_resamples)
    return out


def summarize(
    clap_csv: Path,
    quality_csv: Path,
    artifacts_dir: Path,
    status_json: Path | None,
    extra_status: dict | None = None,
    n_resamples: int = BOOTSTRAP_N_DEFAULT,
    seed: int = 0,
) -> tuple[dict, dict]:
    clap = load_clap_csv(clap_csv)
    quality = load_quality_csv(quality_csv)
    paired = pair_clap_quality(clap, quality)
    corr = spearman_summary(paired)
    contrast = flag_sing_contrast(paired, n_resamples=n_resamples, seed=seed)

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    corr_path = artifacts_dir / "corr_summary.json"
    contrast_path = artifacts_dir / "flag_sing_contrast.json"
    write_json(corr_path, corr)
    write_json(contrast_path, contrast)

    missing_corr = [k for k in CORR_KEYS if k not in corr]
    missing_contrast = [k for k in CONTRAST_BASE_KEYS if k not in contrast]
    if missing_corr or missing_contrast:
        raise SystemExit(
            f"summarize missing keys: corr={missing_corr} contrast={missing_contrast}"
        )
    has_mw = "mw_pvalue" in contrast
    has_boot = all(
        k in contrast
        for k in ("median_diff", "bootstrap_ci_low", "bootstrap_ci_high")
    )
    n1 = contrast["n_flag1"]
    if n1 >= N_FLAG1_MW_MIN and not has_mw:
        raise SystemExit("n_flag1>=10 but mw_pvalue missing")
    if n1 < N_FLAG1_MW_MIN and n1 >= 1 and contrast["n_flag0"] >= 1 and not has_boot:
        raise SystemExit("n_flag1<10 but bootstrap CI fields missing")

    status = {
        "task": "round1_clap_sing",
        "smoke_ok": True,
        "updated_at": _now_iso(),
        "n_clap_rows": int(len(clap)),
        "n_clap_ok": int((clap["clap_ok"] == 1).sum()),
        "n_paired": corr["n_paired"],
        "corr_summary": str(corr_path),
        "flag_sing_contrast": str(contrast_path),
        "quality_csv": str(quality_csv),
        "clap_csv": str(clap_csv),
        "model_id": CLAP_MODEL_ID,
    }
    if extra_status:
        status.update(extra_status)
    if status_json is None:
        status_json = artifacts_dir.parent / "STATUS.json"
    write_json(status_json, status)
    print(f"Wrote {corr_path}", flush=True)
    print(f"Wrote {contrast_path}", flush=True)
    print(f"Wrote {status_json}", flush=True)
    return corr, contrast


def list_audio_files(windows_dir: Path) -> list[Path]:
    if not windows_dir.is_dir():
        raise SystemExit(f"--windows-dir is not a directory: {windows_dir}")
    files = sorted(windows_dir.glob("*.flac"))
    if not files:
        files = sorted(windows_dir.glob("*.wav"))
    if not files:
        raise SystemExit(f"No FLAC/WAV files in {windows_dir}")
    return files


def empty_row(window_id: str, error: str) -> dict:
    return {
        "window_id": window_id,
        "clap_sing": "",
        "clap_speak": "",
        "clap_logit_diff": "",
        "clap_ok": 0,
        "error": error.replace("\n", " ")[:300],
    }


def ok_row(window_id: str, sing: float, speak: float) -> dict:
    return {
        "window_id": window_id,
        "clap_sing": f"{sing:.8g}",
        "clap_speak": f"{speak:.8g}",
        "clap_logit_diff": f"{(sing - speak):.8g}",
        "clap_ok": 1,
        "error": "",
    }


def write_clap_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def estimate_hub_weight_bytes(model_id: str, timeout: float = 30.0) -> int:
    """Sum sibling blob sizes from the Hub API (no weight download)."""
    url = f"https://huggingface.co/api/models/{model_id}?blobs=true"
    req = urllib.request.Request(url, headers={"User-Agent": "cantoai-analysis-clap"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(
            f"WARN Hub size query failed ({exc}); "
            f"using documented estimate {DOCUMENTED_WEIGHT_BYTES} bytes",
            file=sys.stderr,
            flush=True,
        )
        return DOCUMENTED_WEIGHT_BYTES
    total = 0
    for sib in payload.get("siblings") or []:
        size = sib.get("size")
        if isinstance(size, int):
            total += size
    if total <= 0:
        return DOCUMENTED_WEIGHT_BYTES
    return total


def ensure_weight_budget(model_id: str) -> int:
    size = estimate_hub_weight_bytes(model_id)
    print(
        f"Weight download estimate for {model_id}: {size} bytes "
        f"({size / (1024 ** 3):.3f} GiB); cap={MAX_WEIGHT_BYTES}",
        flush=True,
    )
    if size > MAX_WEIGHT_BYTES:
        raise SystemExit(
            f"ABORT: estimated Hub download {size} bytes exceeds 2GB "
            f"({MAX_WEIGHT_BYTES}). Do not download; escalate Tom."
        )
    return size


def load_mono(path: Path, sr: int) -> np.ndarray:
    import librosa
    import soundfile as sf

    audio, file_sr = sf.read(str(path), always_2d=False)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    audio = np.asarray(audio, dtype=np.float32)
    if file_sr != sr:
        audio = librosa.resample(audio, orig_sr=int(file_sr), target_sr=sr)
        audio = np.asarray(audio, dtype=np.float32)
    max_n = sr * CLAP_MAX_SECONDS
    if audio.size > max_n:
        audio = audio[:max_n]
    return audio


class ClapScorer:
    """Lazy CPU CLAP scorer. Construct only when scoring real audio."""

    def __init__(self, model_id: str = CLAP_MODEL_ID):
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        ensure_weight_budget(model_id)
        import torch
        from transformers import ClapModel, ClapProcessor

        torch.set_grad_enabled(False)
        self.device = torch.device("cpu")
        print(f"Loading {model_id} on CPU...", flush=True)
        self.processor = ClapProcessor.from_pretrained(model_id)
        self.model = ClapModel.from_pretrained(model_id)
        self.model.to(self.device)
        self.model.eval()
        self.sr = int(
            getattr(self.processor.feature_extractor, "sampling_rate", CLAP_SR)
            or CLAP_SR
        )
        self._torch = torch

    def score_path(self, path: Path) -> tuple[float, float]:
        audio = load_mono(path, self.sr)
        if audio.size == 0:
            raise ValueError("empty_audio")
        inputs = self.processor(
            text=list(PROMPTS),
            audios=audio,
            sampling_rate=self.sr,
            return_tensors="pt",
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with self._torch.no_grad():
            out = self.model(**inputs)
        logits = out.logits_per_audio[0]
        sing = float(logits[0].item())
        speak = float(logits[1].item())
        return sing, speak


def run_inference(
    windows_dir: Path,
    out_csv: Path,
    limit: int | None,
) -> list[dict]:
    files = list_audio_files(windows_dir)
    if limit is not None:
        files = files[: max(0, limit)]
    scorer = ClapScorer(CLAP_MODEL_ID)
    rows: list[dict] = []
    t0 = time.perf_counter()
    for i, path in enumerate(files, 1):
        wid = path.stem
        print(f"[{i}/{len(files)}] {path.name}", flush=True)
        try:
            sing, speak = scorer.score_path(path)
            rows.append(ok_row(wid, sing, speak))
        except Exception as exc:  # noqa: BLE001 — per-window isolation
            rows.append(empty_row(wid, repr(exc)))
    elapsed = time.perf_counter() - t0
    write_clap_csv(out_csv, rows)
    n_ok = sum(int(r["clap_ok"]) for r in rows)
    print(
        f"Wrote {out_csv} n={len(rows)} clap_ok={n_ok} elapsed_s={elapsed:.1f}",
        flush=True,
    )
    return rows


def synthetic_rows_from_quality(quality: pd.DataFrame, limit: int | None) -> list[dict]:
    df = quality
    if limit is not None:
        df = df.iloc[: max(0, limit)]
    rows: list[dict] = []
    for rec in df.itertuples(index=False):
        sp = rec.singing_prob
        if pd.isna(sp):
            rows.append(empty_row(str(rec.window_id), "synthetic_nan_singing_prob"))
            continue
        sing = float(sp)
        speak = float(1.0 - sp)
        rows.append(ok_row(str(rec.window_id), sing, speak))
    return rows


def default_status_path(artifacts_dir: Path | None, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    if artifacts_dir is not None:
        return artifacts_dir.parent / "STATUS.json"
    return None


# ---------------------------------------------------------------------------
# Fixtures / self-test (no audio, no weights)
# ---------------------------------------------------------------------------

TINY_CLAP_ROWS = [
    ok_row("w000", 0.10, 0.90),
    ok_row("w001", 0.20, 0.80),
    ok_row("w002", 0.30, 0.70),
    ok_row("w003", 0.40, 0.60),
    ok_row("w004", 0.50, 0.50),
    ok_row("w005", 0.85, 0.15),
    ok_row("w006", 0.95, 0.05),
    empty_row("w_fail", "synthetic_error"),
    ok_row("w_orphan", 0.55, 0.45),
]
TINY_QUALITY_ROWS = [
    {"window_id": "w000", "singing_prob": 0.01, "flag_sing": 0},
    {"window_id": "w001", "singing_prob": 0.02, "flag_sing": 0},
    {"window_id": "w002", "singing_prob": 0.03, "flag_sing": 0},
    {"window_id": "w003", "singing_prob": 0.04, "flag_sing": 0},
    {"window_id": "w004", "singing_prob": 0.05, "flag_sing": 0},
    {"window_id": "w005", "singing_prob": 0.50, "flag_sing": 1},
    {"window_id": "w006", "singing_prob": 0.80, "flag_sing": 1},
    {"window_id": "w_fail", "singing_prob": 0.10, "flag_sing": 0},
    {"window_id": "w_quality_only", "singing_prob": 0.99, "flag_sing": 1},
]


def write_quality_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["window_id", "singing_prob", "flag_sing"]
        )
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"SELF-TEST FAILED: {msg}")


def _assert_close(a: Any, b: float, msg: str, tol: float = 1e-9) -> None:
    _assert(a is not None and abs(float(a) - b) < tol, f"{msg}: {a} vs {b}")


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="clap_selftest_") as tmp:
        tmp_path = Path(tmp)
        clap_path = tmp_path / "clap_tiny.csv"
        quality_path = tmp_path / "quality_with_flags_tiny.csv"
        artifacts = tmp_path / "artifacts"
        status_path = tmp_path / "STATUS.json"
        write_clap_csv(clap_path, TINY_CLAP_ROWS)
        write_quality_csv(quality_path, TINY_QUALITY_ROWS)

        corr, contrast = summarize(
            clap_path,
            quality_path,
            artifacts,
            status_path,
            extra_status={"dry_run": True, "limit": None, "self_test": "tiny"},
            seed=0,
        )
        _assert(corr["n_paired"] == 7, f"n_paired={corr['n_paired']} expected 7")
        _assert(
            corr["spearman_clap_vs_panns"] is not None
            and abs(corr["spearman_clap_vs_panns"] - 1.0) < 1e-12,
            f"spearman={corr['spearman_clap_vs_panns']} expected 1.0",
        )
        _assert(contrast["n_flag1"] == 2, f"n_flag1={contrast['n_flag1']}")
        _assert(contrast["n_flag0"] == 5, f"n_flag0={contrast['n_flag0']}")
        _assert_close(contrast["median_clap_flag1"], 0.90, "median flag1")
        _assert_close(contrast["median_clap_flag0"], 0.30, "median flag0")
        _assert("mw_pvalue" not in contrast, "tiny set must use bootstrap, not MW")
        _assert("bootstrap_ci_low" in contrast, "missing bootstrap_ci_low")
        _assert("bootstrap_ci_high" in contrast, "missing bootstrap_ci_high")
        _assert_close(contrast["median_diff"], 0.60, "median_diff")
        status = json.loads(status_path.read_text(encoding="utf-8"))
        _assert(status.get("smoke_ok") is True, "smoke_ok")

        # Independent recompute of n_paired / spearman
        clap = load_clap_csv(clap_path)
        quality = load_quality_csv(quality_path)
        paired = pair_clap_quality(clap, quality)
        _assert(len(paired) == corr["n_paired"], "n_paired != inner-join count")

        # n_flag1>=10 → mw_pvalue branch
        mw_rows_q = []
        mw_rows_c = []
        for i in range(12):
            mw_rows_q.append(
                {"window_id": f"a{i:02d}", "singing_prob": 0.01 * (i + 1), "flag_sing": 0}
            )
            mw_rows_c.append(ok_row(f"a{i:02d}", 0.10 + 0.01 * i, 0.90))
        for i in range(12):
            mw_rows_q.append(
                {
                    "window_id": f"b{i:02d}",
                    "singing_prob": 0.50 + 0.01 * i,
                    "flag_sing": 1,
                }
            )
            mw_rows_c.append(ok_row(f"b{i:02d}", 0.70 + 0.01 * i, 0.20))
        clap_mw = tmp_path / "clap_mw.csv"
        quality_mw = tmp_path / "quality_mw.csv"
        write_clap_csv(clap_mw, mw_rows_c)
        write_quality_csv(quality_mw, mw_rows_q)
        _, contrast_mw = summarize(
            clap_mw,
            quality_mw,
            tmp_path / "artifacts_mw",
            tmp_path / "STATUS_mw.json",
            extra_status={"self_test": "mw"},
        )
        _assert(contrast_mw["n_flag1"] == 12, "mw n_flag1")
        _assert("mw_pvalue" in contrast_mw, "expected mw_pvalue")
        _assert("bootstrap_ci_low" not in contrast_mw, "MW branch should omit CI")
        _assert(contrast_mw["mw_pvalue"] < 0.05, "synthetic MW should be <0.05")

        # Bare quality CSV (no flag_sing) must fail
        bare = tmp_path / "window_quality.csv"
        with bare.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f, fieldnames=["window_id", "singing_prob", "music_prob"]
            )
            w.writeheader()
            w.writerow(
                {"window_id": "w000", "singing_prob": 0.1, "music_prob": 0.2}
            )
        raised = False
        try:
            load_quality_csv(bare)
        except SystemExit as exc:
            raised = True
            _assert("with_flags" in str(exc), f"error text: {exc}")
        _assert(raised, "bare window_quality.csv should be rejected")

        # --dry-run path: synthetic clap from quality, then summarize
        dry_out = tmp_path / "dry" / "window_clap_sing.csv"
        dry_art = tmp_path / "dry" / "artifacts"
        dry_status = tmp_path / "dry" / "STATUS.json"
        q = load_quality_csv(quality_path)
        rows = synthetic_rows_from_quality(q, limit=8)
        write_clap_csv(dry_out, rows)
        summarize(
            dry_out,
            quality_path,
            dry_art,
            dry_status,
            extra_status={"dry_run": True, "limit": 8},
        )
        dry_status_obj = json.loads(dry_status.read_text(encoding="utf-8"))
        _assert(dry_status_obj.get("smoke_ok") is True, "dry-run smoke_ok")

    print("SELF-TEST PASSED", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Score window FLACs with LAION-CLAP (sing vs speak) and/or "
            "summarize Spearman vs PANNs singing_prob."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_clap_sing.py --help

  python scripts/run_clap_sing.py --summarize \\
    --clap-csv fixtures/clap_tiny.csv \\
    --quality-csv fixtures/quality_with_flags_tiny.csv \\
    --artifacts-dir /tmp/round1_clap/artifacts \\
    --status-json /tmp/round1_clap/STATUS.json

  python scripts/run_clap_sing.py --dry-run --limit 8 \\
    --quality-csv fixtures/quality_with_flags_tiny.csv \\
    --out /tmp/round1_clap/window_clap_sing.csv \\
    --artifacts-dir /tmp/round1_clap/artifacts

  python scripts/run_clap_sing.py --self-test

  python scripts/run_clap_sing.py \\
    --windows-dir /workspace/cantoai/corpus/dataset_v2/work/windows \\
    --quality-csv /workspace/cantoai/analysis/task2_window_quality/window_quality_with_flags.csv \\
    --out /workspace/cantoai/analysis/ROUND-1/window_clap_sing.csv \\
    --artifacts-dir /workspace/cantoai/analysis/ROUND-1/artifacts \\
    --limit 20
""",
    )
    p.add_argument("--windows-dir", type=Path, help="Directory of window FLAC files")
    p.add_argument(
        "--quality-csv",
        type=Path,
        help="window_quality_with_flags.csv (must include flag_sing + singing_prob)",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Output clap CSV (window_clap_sing.csv)",
    )
    p.add_argument(
        "--clap-csv",
        type=Path,
        help="Existing clap CSV for --summarize (defaults to --out)",
    )
    p.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Directory for corr_summary.json and flag_sing_contrast.json",
    )
    p.add_argument(
        "--status-json",
        type=Path,
        help="STATUS.json path (default: artifacts-dir/../STATUS.json)",
    )
    p.add_argument("--limit", type=int, default=None, help="Score at most N windows")
    p.add_argument(
        "--summarize",
        action="store_true",
        help="Skip inference; write artifact JSON from --clap-csv + --quality-csv",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="No model load: write synthetic clap scores from quality CSV and summarize",
    )
    p.add_argument(
        "--self-test",
        action="store_true",
        help="In-memory fixture checks for summarize math + CLI guards (no weights)",
    )
    p.add_argument("--seed", type=int, default=0, help="Bootstrap RNG seed")
    p.add_argument(
        "--bootstrap-n",
        type=int,
        default=BOOTSTRAP_N_DEFAULT,
        help="Bootstrap resamples when n_flag1<10 (default 2000)",
    )
    p.add_argument(
        "--check-weights",
        action="store_true",
        help="Query Hub for weight size and exit (no download of pytorch_model.bin)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        run_self_test()
        return 0

    if args.check_weights:
        size = ensure_weight_budget(CLAP_MODEL_ID)
        print(json.dumps({"model_id": CLAP_MODEL_ID, "bytes": size}, indent=2))
        return 0

    if args.summarize:
        if not args.quality_csv or not args.artifacts_dir:
            raise SystemExit("--summarize requires --quality-csv and --artifacts-dir")
        clap_csv = args.clap_csv or args.out
        if not clap_csv:
            raise SystemExit("--summarize requires --clap-csv or --out")
        summarize(
            clap_csv,
            args.quality_csv,
            args.artifacts_dir,
            default_status_path(args.artifacts_dir, args.status_json),
            extra_status={"limit": args.limit, "dry_run": bool(args.dry_run)},
            n_resamples=args.bootstrap_n,
            seed=args.seed,
        )
        return 0

    if args.dry_run:
        if not args.quality_csv or not args.out:
            raise SystemExit("--dry-run requires --quality-csv and --out")
        quality = load_quality_csv(args.quality_csv)
        rows = synthetic_rows_from_quality(quality, args.limit)
        write_clap_csv(args.out, rows)
        print(f"Wrote synthetic {args.out} n={len(rows)} (dry-run, no CLAP weights)", flush=True)
        if args.artifacts_dir:
            summarize(
                args.out,
                args.quality_csv,
                args.artifacts_dir,
                default_status_path(args.artifacts_dir, args.status_json),
                extra_status={"limit": args.limit, "dry_run": True, "smoke_ok": True},
                n_resamples=args.bootstrap_n,
                seed=args.seed,
            )
        return 0

    if not args.windows_dir or not args.out:
        raise SystemExit("inference requires --windows-dir and --out (or use --dry-run / --summarize)")
    if not args.quality_csv:
        raise SystemExit(
            "inference requires --quality-csv (with_flags file) even before summarize"
        )
    load_quality_csv(args.quality_csv)  # fail fast if bare window_quality.csv
    run_inference(args.windows_dir, args.out, args.limit)
    if args.artifacts_dir:
        summarize(
            args.out,
            args.quality_csv,
            args.artifacts_dir,
            default_status_path(args.artifacts_dir, args.status_json),
            extra_status={
                "limit": args.limit,
                "dry_run": False,
                "windows_dir": str(args.windows_dir),
            },
            n_resamples=args.bootstrap_n,
            seed=args.seed,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
