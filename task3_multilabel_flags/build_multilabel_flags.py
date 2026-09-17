#!/usr/bin/env python3
"""Task 3 (prep): multi-label content flags from video titles (non-exclusive).

Reuses KEYWORDS / FILM_RELATED_CORE from task1. Does NOT apply task1's
mutual-exclusion priority. Optionally left-joins singing_prob from task2
trial/partial CSVs when present.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import sqlite3

ROOT = Path("/workspace/cantoai")
DB = ROOT / "corpus/dataset_v2/work/corpus.sqlite"
OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

TASK1_PY = ROOT / "analysis/task1_content_labels/label_content_types.py"

# Candidate singing_prob sources (first existing wins for left-join coverage;
# multiple files are outer-merged on window_id with prefer-non-null).
SINGING_PROB_CANDIDATES = [
    ROOT / "analysis/task2_window_quality/window_quality.csv",
    ROOT / "analysis/task2_window_quality/artifacts/window_quality.csv",
    ROOT / "analysis/task2_window_quality/trial_50_quality.csv",
    ROOT / "analysis/task2_window_quality/trial_50_quality_with_flags.csv",
    ROOT / "analysis/task2_window_quality/artifacts/smoke.csv",
    ROOT / "analysis/task2_window_quality/artifacts/smoke_with_flags.csv",
]

SINGING_PROB_THRESHOLD = 0.2


def _load_task1_keywords():
    spec = importlib.util.spec_from_file_location("task1_label_content_types", TASK1_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load task1 module from {TASK1_PY}")
    mod = importlib.util.module_from_spec(spec)
    # Avoid executing matplotlib-heavy main; only load module body.
    # The module defines constants at import time and only runs main under __main__.
    sys.modules["task1_label_content_types"] = mod
    spec.loader.exec_module(mod)
    return mod.KEYWORDS, list(mod.FILM_RELATED_CORE)


def matched_keywords(title: str, keywords: list[str]) -> str:
    t = title or ""
    return "|".join(k for k in keywords if k in t)


def has_any(title: str, keywords: list[str]) -> bool:
    t = title or ""
    return any(k in t for k in keywords)


def load_singing_prob() -> tuple[pd.DataFrame, list[str]]:
    """Return DataFrame[window_id, singing_prob] and list of source paths used."""
    frames = []
    used = []
    for path in SINGING_PROB_CANDIDATES:
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        # normalize id column
        if "window_id" not in df.columns and "uid" in df.columns:
            df = df.rename(columns={"uid": "window_id"})
        if "window_id" not in df.columns or "singing_prob" not in df.columns:
            continue
        sub = df[["window_id", "singing_prob"]].copy()
        sub["singing_prob"] = pd.to_numeric(sub["singing_prob"], errors="coerce")
        frames.append(sub)
        used.append(str(path))
    if not frames:
        return pd.DataFrame(columns=["window_id", "singing_prob"]), []
    merged = pd.concat(frames, ignore_index=True)
    # prefer first non-null per window_id (candidate order = priority)
    merged = merged.dropna(subset=["singing_prob"]).drop_duplicates(
        subset=["window_id"], keep="first"
    )
    return merged, used


def main() -> None:
    KEYWORDS, FILM_RELATED_CORE = _load_task1_keywords()

    con = sqlite3.connect(DB)
    videos = pd.read_sql_query(
        "SELECT video_id, title, upload_date, n_windows, speech_s FROM videos", con
    )
    windows = pd.read_sql_query(
        "SELECT uid, video_id, tier, idx, start, end, dur FROM windows", con
    )
    con.close()

    rows = []
    for r in videos.itertuples(index=False):
        title = r.title or ""
        m_parody = matched_keywords(title, KEYWORDS["parody"])
        m_song = matched_keywords(title, KEYWORDS["song"])
        m_rec = matched_keywords(title, KEYWORDS["recitation"])
        m_film = matched_keywords(title, KEYWORDS["film_clip"])
        m_core = matched_keywords(title, FILM_RELATED_CORE)

        parody_flag = int(bool(m_parody))
        song_flag = int(bool(m_song))
        recitation_flag = int(bool(m_rec))
        film_flag = int(bool(m_film))
        film_related_core = int(bool(m_core))
        contemporary_only = int(
            parody_flag == 0
            and song_flag == 0
            and recitation_flag == 0
            and film_flag == 0
        )

        all_matched = []
        if m_parody:
            all_matched.append(f"parody:{m_parody}")
        if m_song:
            all_matched.append(f"song:{m_song}")
        if m_rec:
            all_matched.append(f"recitation:{m_rec}")
        if m_film:
            all_matched.append(f"film_clip:{m_film}")

        rows.append(
            {
                "video_id": r.video_id,
                "title": r.title,
                "upload_date": r.upload_date,
                "n_windows": r.n_windows,
                "speech_s": r.speech_s,
                "parody_flag": parody_flag,
                "song_flag": song_flag,
                "recitation_flag": recitation_flag,
                "film_flag": film_flag,
                "film_related_core": film_related_core,
                "contemporary_only": contemporary_only,
                "matched_parody": m_parody,
                "matched_song": m_song,
                "matched_recitation": m_rec,
                "matched_film_clip": m_film,
                "matched_film_related_core": m_core,
                "matched_keywords": ";".join(all_matched),
            }
        )

    video_flags = pd.DataFrame(rows).sort_values("video_id").reset_index(drop=True)
    video_path = OUT / "video_multilabel_flags.csv"
    video_flags.to_csv(video_path, index=False)

    # Flag counts (video-level only; no stratified agreement)
    flag_cols = [
        "parody_flag",
        "song_flag",
        "recitation_flag",
        "film_flag",
        "film_related_core",
        "contemporary_only",
    ]
    count_rows = []
    n_vid = len(video_flags)
    for col in flag_cols:
        n = int(video_flags[col].sum())
        count_rows.append(
            {
                "flag": col,
                "n_videos": n,
                "share_videos": float(n / n_vid) if n_vid else float("nan"),
            }
        )
    # co-occurrence: any multi-hit among the four content flags
    four = video_flags[
        ["parody_flag", "song_flag", "recitation_flag", "film_flag"]
    ].sum(axis=1)
    count_rows.append(
        {
            "flag": "multi_content_flag_ge2",
            "n_videos": int((four >= 2).sum()),
            "share_videos": float((four >= 2).mean()) if n_vid else float("nan"),
        }
    )
    counts = pd.DataFrame(count_rows)
    counts_path = OUT / "flag_counts_videos.csv"
    counts.to_csv(counts_path, index=False)

    # Window-level: propagate video flags + optional singing_prob
    singing, singing_sources = load_singing_prob()
    win = windows.merge(
        video_flags[
            [
                "video_id",
                "parody_flag",
                "song_flag",
                "recitation_flag",
                "film_flag",
                "film_related_core",
                "contemporary_only",
                "matched_keywords",
            ]
        ],
        on="video_id",
        how="left",
    )
    win = win.rename(columns={"uid": "window_id"})
    if len(singing):
        win = win.merge(singing, on="window_id", how="left")
    else:
        win["singing_prob"] = pd.NA

    # dialogue_film: film_flag=1 AND singing_prob < 0.2 (only when singing_prob present)
    sp = win["singing_prob"]
    dialogue = pd.Series(pd.NA, index=win.index, dtype="Int64")
    has_sp = sp.notna()
    dialogue.loc[has_sp] = (
        (win.loc[has_sp, "film_flag"] == 1) & (sp.loc[has_sp] < SINGING_PROB_THRESHOLD)
    ).astype(int)
    win["dialogue_film"] = dialogue

    win_cols = [
        "window_id",
        "video_id",
        "tier",
        "idx",
        "start",
        "end",
        "dur",
        "parody_flag",
        "song_flag",
        "recitation_flag",
        "film_flag",
        "film_related_core",
        "contemporary_only",
        "matched_keywords",
        "singing_prob",
        "dialogue_film",
    ]
    win_out = win[win_cols].sort_values(["video_id", "idx"]).reset_index(drop=True)
    win_path = OUT / "window_multilabel_flags.csv"
    win_out.to_csv(win_path, index=False)

    # Write a small meta sidecar for README / reproducibility notes
    meta = {
        "n_videos": int(n_vid),
        "n_windows": int(len(win_out)),
        "n_windows_with_singing_prob": int(win_out["singing_prob"].notna().sum()),
        "singing_prob_sources": singing_sources,
        "singing_prob_threshold_for_dialogue_film": SINGING_PROB_THRESHOLD,
        "flag_counts": counts.to_dict(orient="records"),
    }
    import json

    (OUT / "_build_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("Wrote", video_path)
    print("Wrote", win_path)
    print("Wrote", counts_path)
    print(counts.to_string(index=False))
    print(
        f"singing_prob coverage: {meta['n_windows_with_singing_prob']}/{meta['n_windows']}"
    )
    print("sources:", singing_sources)


if __name__ == "__main__":
    main()
