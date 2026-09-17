#!/usr/bin/env python3
"""Window-level quality features: music_prob, singing_prob, snr_db, dnsmos_ovrl.

Definitions
-----------
music_prob / singing_prob (PANNs Cnn14, AudioSet clipwise sigmoid):
  - Resample to 32 kHz mono.
  - music_prob   = clipwise[Music=137]
  - singing_prob = max(clipwise[Singing=27], Male/Female/Child singing=32/33/34)
  Clip-level probability (not time fraction); values in [0, 1].

snr_db (brouhaha-vad ONNX, FredrikKarlssonSpeech/brouhaha-vad-onnx):
  - 16 kHz mono, 6 s chunks with 1 s hop (5 s overlap), average overlapping frames.
  - Output channels: vad, snr_raw, c50_raw. If snr looks like [0,1], map to dB via
    snr_db = -15 + snr_raw * 95 (paper range). Else treat as already dB.
  - Aggregate: mean SNR over frames with vad >= 0.5; if none, mean over all frames.

dnsmos_ovrl (Microsoft DNS-Challenge DNSMOS ONNX sig_bak_ovr.onnx):
  - 16 kHz; repeat-pad to >= 9.01 s; 1 s hops; polyfit OVRL mean (non-personalized).
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import onnxruntime as ort
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
WIN_DIR = Path("/workspace/cantoai/corpus/dataset_v2/work/windows")
DB_PATH = Path("/workspace/cantoai/corpus/dataset_v2/work/corpus.sqlite")

MUSIC_IDX = 137
SINGING_IDXS = (27, 32, 33, 34)  # Singing + Male/Female/Child singing
PANNS_SR = 32000
BROU_SR = 16000
BROU_CHUNK = 96000  # 6 s
BROU_HOP = 16000  # 1 s
DNSMOS_SR = 16000
DNSMOS_INPUT_LEN = 9.01

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cnn14 import Cnn14  # noqa: E402


def flac_path(video_id: str, idx: int) -> Path:
    return WIN_DIR / f"{video_id}_{idx:03d}.flac"


def load_mono(path: Path, sr: int) -> np.ndarray:
    audio, file_sr = sf.read(str(path), always_2d=False)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    audio = audio.astype(np.float32)
    if file_sr != sr:
        audio = librosa.resample(audio, orig_sr=file_sr, target_sr=sr)
    return audio.astype(np.float32)


def list_windows_from_db(db_path: Path = DB_PATH):
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT uid, video_id, idx, flag_sing, dur FROM windows ORDER BY uid"
    ).fetchall()
    conn.close()
    out = []
    for uid, video_id, idx, flag_sing, dur in rows:
        p = flac_path(video_id, idx)
        out.append(
            {
                "window_id": uid,
                "video_id": video_id,
                "idx": idx,
                "flag_sing": int(flag_sing or 0),
                "dur": float(dur),
                "path": str(p),
                "exists": p.exists(),
            }
        )
    return out


def sample_trial(windows, n=50, seed=42):
    rng = np.random.default_rng(seed)
    singing = [w for w in windows if w["flag_sing"] == 1]
    others = [w for w in windows if w["flag_sing"] != 1]
    chosen = list(singing)
    need = n - len(chosen)
    if need > 0:
        idxs = rng.choice(len(others), size=min(need, len(others)), replace=False)
        chosen.extend(others[i] for i in idxs)
    # stable order by window_id
    chosen = sorted(chosen, key=lambda w: w["window_id"])
    return chosen[:n]


# -------------------- PANNs --------------------
class PannsScorer:
    def __init__(self, ckpt: Path, device="cpu"):
        self.device = device
        self.model = Cnn14(sample_rate=PANNS_SR, classes_num=527)
        ckpt_obj = torch.load(str(ckpt), map_location=device, weights_only=False)
        state = ckpt_obj["model"] if isinstance(ckpt_obj, dict) and "model" in ckpt_obj else ckpt_obj
        self.model.load_state_dict(state)
        self.model.to(device)
        self.model.eval()

    def score(self, path: Path):
        audio = load_mono(path, PANNS_SR)
        # pad tiny clips
        if len(audio) < PANNS_SR // 2:
            audio = np.pad(audio, (0, PANNS_SR // 2 - len(audio)))
        x = torch.from_numpy(audio[None, :]).float().to(self.device)
        with torch.no_grad():
            out = self.model(x, None)
            clip = out["clipwise_output"][0].cpu().numpy()
        music = float(clip[MUSIC_IDX])
        singing = float(np.max(clip[list(SINGING_IDXS)]))
        return music, singing


# -------------------- Brouhaha SNR --------------------
class BrouhahaSNR:
    def __init__(self, onnx_path: Path):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) // 2)
        self.sess = ort.InferenceSession(
            str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.in_name = self.sess.get_inputs()[0].name
        self.out_name = self.sess.get_outputs()[0].name
        # probe scale once
        self._snr_is_unit = None

    def _maybe_to_db(self, snr):
        # Heuristic: if vast majority in [0,1], treat as sigmoid and map.
        if self._snr_is_unit is None:
            self._snr_is_unit = bool(np.nanpercentile(snr, 95) <= 1.5)
        if self._snr_is_unit:
            return -15.0 + snr * 95.0
        return snr

    def score(self, path: Path) -> float:
        audio = load_mono(path, BROU_SR)
        if len(audio) == 0:
            return float("nan")
        # pad to at least one chunk
        if len(audio) < BROU_CHUNK:
            audio = np.pad(audio, (0, BROU_CHUNK - len(audio)))
        # sliding chunks
        starts = list(range(0, max(1, len(audio) - BROU_CHUNK + 1), BROU_HOP))
        if starts[-1] + BROU_CHUNK < len(audio):
            starts.append(len(audio) - BROU_CHUNK)
        # accumulate per-sample then average (overlap-add style on frames)
        all_vad = []
        all_snr = []
        for st in starts:
            chunk = audio[st : st + BROU_CHUNK]
            if len(chunk) < BROU_CHUNK:
                chunk = np.pad(chunk, (0, BROU_CHUNK - len(chunk)))
            wave = chunk.astype(np.float32)[None, None, :]
            scores = self.sess.run([self.out_name], {self.in_name: wave})[0]  # (1, T, 3)
            s = scores[0]
            all_vad.append(s[:, 0])
            all_snr.append(s[:, 1])
        vad = np.concatenate(all_vad)
        snr = np.concatenate(all_snr)
        snr_db = self._maybe_to_db(snr)
        speech = vad >= 0.5
        if np.any(speech):
            return float(np.mean(snr_db[speech]))
        return float(np.mean(snr_db))


# -------------------- DNSMOS --------------------
class DNSMOS:
    def __init__(self, primary: Path, p808: Path):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) // 2)
        self.primary = ort.InferenceSession(
            str(primary), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.p808 = ort.InferenceSession(
            str(p808), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.p_ovr = np.poly1d([-0.06766283, 1.11546468, 0.04602535])

    def audio_melspec(self, audio, n_mels=120, frame_size=320, hop_length=160, sr=16000):
        mel_spec = librosa.feature.melspectrogram(
            y=audio, sr=sr, n_fft=frame_size + 1, hop_length=hop_length, n_mels=n_mels
        )
        mel_spec = (librosa.power_to_db(mel_spec, ref=np.max) + 40) / 40
        return mel_spec.T

    def score(self, path: Path) -> float:
        aud, input_fs = sf.read(str(path))
        if aud.ndim > 1:
            aud = np.mean(aud, axis=1)
        if input_fs != DNSMOS_SR:
            audio = librosa.resample(aud.astype(np.float32), orig_sr=input_fs, target_sr=DNSMOS_SR)
        else:
            audio = aud.astype(np.float32)
        len_samples = int(DNSMOS_INPUT_LEN * DNSMOS_SR)
        if len(audio) == 0:
            return float("nan")
        # repeat-pad to at least one hop window
        while len(audio) < len_samples:
            audio = np.append(audio, audio)
        num_hops = int(np.floor(len(audio) / DNSMOS_SR) - DNSMOS_INPUT_LEN) + 1
        if num_hops < 1:
            num_hops = 1
        ovr_vals = []
        for idx in range(num_hops):
            seg = audio[int(idx * DNSMOS_SR) : int((idx + DNSMOS_INPUT_LEN) * DNSMOS_SR)]
            if len(seg) < len_samples:
                continue
            inp = np.array(seg, dtype=np.float32)[None, :]
            # p808 not needed for OVRL but keeps parity with reference code path
            _ = self.p808.run(
                None,
                {"input_1": np.array(self.audio_melspec(audio=seg[:-160]), dtype=np.float32)[None, :, :]},
            )
            mos_sig_raw, mos_bak_raw, mos_ovr_raw = self.primary.run(None, {"input_1": inp})[0][0]
            ovr = float(self.p_ovr(mos_ovr_raw))
            ovr_vals.append(ovr)
        if not ovr_vals:
            return float("nan")
        return float(np.mean(ovr_vals))


def run_tool(name, scorer_fn, windows, out_key_map):
    """scorer_fn(path) -> dict of metric values. Returns timing + results + failures."""
    t0 = time.perf_counter()
    results = {}
    failures = []
    for w in windows:
        try:
            vals = scorer_fn(Path(w["path"]))
            results[w["window_id"]] = vals
        except Exception as e:
            failures.append({"window_id": w["window_id"], "tool": name, "error": repr(e)})
            results[w["window_id"]] = {k: float("nan") for k in out_key_map}
    elapsed = time.perf_counter() - t0
    return elapsed, results, failures


def merge_results(windows, panns_res, snr_res, dns_res):
    rows = []
    for w in windows:
        wid = w["window_id"]
        m = panns_res.get(wid, {})
        s = snr_res.get(wid, {})
        d = dns_res.get(wid, {})
        rows.append(
            {
                "window_id": wid,
                "music_prob": m.get("music_prob", float("nan")),
                "singing_prob": m.get("singing_prob", float("nan")),
                "snr_db": s.get("snr_db", float("nan")),
                "dnsmos_ovrl": d.get("dnsmos_ovrl", float("nan")),
                "flag_sing": w.get("flag_sing", 0),
            }
        )
    return rows


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="If set, trial sample of N windows")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-csv", type=str, default=None)
    ap.add_argument("--timing-json", type=str, default=None)
    ap.add_argument("--window-ids", type=str, default=None, help="Comma-separated window_ids")
    ap.add_argument("--skip-panns", action="store_true")
    ap.add_argument("--skip-snr", action="store_true")
    ap.add_argument("--skip-dnsmos", action="store_true")
    args = ap.parse_args()

    windows_all = list_windows_from_db()
    missing = [w for w in windows_all if not w["exists"]]
    if missing:
        print(f"WARN missing flacs: {len(missing)}", file=sys.stderr)

    if args.window_ids:
        want = set(args.window_ids.split(","))
        windows = [w for w in windows_all if w["window_id"] in want]
    elif args.limit:
        windows = sample_trial(windows_all, n=args.limit, seed=args.seed)
    else:
        windows = windows_all

    print(f"Processing {len(windows)} windows (of {len(windows_all)})", flush=True)

    timing = {
        "n_windows": len(windows),
        "n_corpus": len(windows_all),
        "seed": args.seed if args.limit else None,
        "window_ids": [w["window_id"] for w in windows],
        "singing_ids_in_sample": [w["window_id"] for w in windows if w["flag_sing"] == 1],
        "tools": {},
        "failures": [],
    }

    panns_res, snr_res, dns_res = {}, {}, {}

    if not args.skip_panns:
        print("Loading PANNs Cnn14...", flush=True)
        panns = PannsScorer(MODELS / "Cnn14_mAP=0.431.pth", device="cpu")

        def panns_fn(p):
            m, s = panns.score(p)
            return {"music_prob": m, "singing_prob": s}

        t, panns_res, fails = run_tool("panns", panns_fn, windows, ["music_prob", "singing_prob"])
        timing["tools"]["panns_music_singing"] = {
            "seconds": t,
            "failures": len(fails),
            "sec_per_window": t / max(1, len(windows)),
        }
        timing["failures"].extend(fails)
        print(f"PANNs done in {t:.1f}s ({t/len(windows):.3f}s/win), fails={len(fails)}", flush=True)
        del panns
        gc.collect()

    if not args.skip_snr:
        print("Loading Brouhaha ONNX...", flush=True)
        brou = BrouhahaSNR(MODELS / "brouhaha.onnx")

        def snr_fn(p):
            return {"snr_db": brou.score(p)}

        t, snr_res, fails = run_tool("brouhaha_snr", snr_fn, windows, ["snr_db"])
        timing["tools"]["brouhaha_snr"] = {
            "seconds": t,
            "failures": len(fails),
            "sec_per_window": t / max(1, len(windows)),
            "snr_unit_interval_mapped": brou._snr_is_unit,
        }
        timing["failures"].extend(fails)
        print(f"Brouhaha done in {t:.1f}s ({t/len(windows):.3f}s/win), fails={len(fails)}", flush=True)
        del brou
        gc.collect()

    if not args.skip_dnsmos:
        print("Loading DNSMOS ONNX...", flush=True)
        dns = DNSMOS(MODELS / "sig_bak_ovr.onnx", MODELS / "model_v8.onnx")

        def dns_fn(p):
            return {"dnsmos_ovrl": dns.score(p)}

        t, dns_res, fails = run_tool("dnsmos", dns_fn, windows, ["dnsmos_ovrl"])
        timing["tools"]["dnsmos_ovrl"] = {
            "seconds": t,
            "failures": len(fails),
            "sec_per_window": t / max(1, len(windows)),
        }
        timing["failures"].extend(fails)
        print(f"DNSMOS done in {t:.1f}s ({t/len(windows):.3f}s/win), fails={len(fails)}", flush=True)
        del dns
        gc.collect()

    rows = merge_results(windows, panns_res, snr_res, dns_res)

    # estimate
    total_sec = sum(v["seconds"] for v in timing["tools"].values())
    n = max(1, len(windows))
    est_hours = (total_sec / n) * len(windows_all) / 3600.0
    timing["trial_total_seconds"] = total_sec
    timing["est_hours_full_4911"] = est_hours
    timing["est_formula"] = "(t_n / n) * 4911 / 3600"

    if args.out_csv:
        out = Path(args.out_csv)
    elif args.limit:
        out = ROOT / "trial_50_quality.csv"
    else:
        out = ROOT / "window_quality.csv"
    fields = ["window_id", "music_prob", "singing_prob", "snr_db", "dnsmos_ovrl"]
    write_csv(out, rows, fields)
    # also keep flag for analysis
    write_csv(out.with_name(out.stem + "_with_flags.csv"), rows, fields + ["flag_sing"])
    print(f"Wrote {out} ({len(rows)} rows)", flush=True)

    if args.timing_json:
        tj = Path(args.timing_json)
    elif args.limit:
        tj = ROOT / "trial_50_timing.json"
    else:
        tj = ROOT / "full_timing.json"
    with open(tj, "w") as f:
        json.dump(timing, f, indent=2)
    print(f"Wrote {tj}; est_hours={est_hours:.3f}", flush=True)


if __name__ == "__main__":
    main()
