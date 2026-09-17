#!/usr/bin/env python3
"""Validate task-brief self-checks on sample outputs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REQUIRED_FILES = [
    "agreement_by_onset.csv",
    "agreement_by_coda.csv",
    "agreement_by_tone.csv",
    "agreement_by_snr.csv",
    "agreement_by_singing.csv",
    "agreement_by_rate.csv",
    "summary_contrast.csv",
]

REQUIRED_COLS = [
    "subset",
    "bin",
    "n_syllables",
    "n_videos",
    "agree_syl",
    "agree_syl_ci_low",
    "agree_syl_ci_high",
    "agree_video_median",
    "agree_video_median_ci_low",
    "agree_video_median_ci_high",
]


def check_outputs(out_dir: Path, max_videos: int = 5) -> int:
    errors: list[str] = []

    for name in REQUIRED_FILES:
        path = out_dir / name
        if not path.exists():
            errors.append(f"missing file: {name}")
            continue
        df = pd.read_csv(path)
        if name == "summary_contrast.csv":
            if len(df) == 0:
                errors.append(f"{name}: empty")
            continue
        missing = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing:
            errors.append(f"{name}: missing columns {missing}")
            continue
        if df["n_videos"].max() > max_videos:
            errors.append(
                f"{name}: n_videos max {df['n_videos'].max()} exceeds {max_videos}"
            )
        if not (df["subset"] == "film").any():
            errors.append(f"{name}: no subset=film row")
        if not (df["subset"] == "contemporary").any():
            errors.append(f"{name}: no subset=contemporary row")

    if errors:
        print("SELF-CHECK FAILED:")
        for e in errors:
            print(" -", e)
        return 1

    print("SELF-CHECK PASSED")
    print(f"  output dir: {out_dir}")
    print(f"  required files: {len(REQUIRED_FILES)}")
    print(f"  n_videos cap: {max_videos}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("task3_hypothesis_strata/_sample_out"),
    )
    args = parser.parse_args()
    return check_outputs(args.out)


if __name__ == "__main__":
    sys.exit(main())
