"""ROUND-3 CLI writes metrics and STATUS (smoke_ok on fixtures)."""

from __future__ import annotations

import json
from pathlib import Path

from src.round3 import run

ROOT = Path(__file__).resolve().parents[1]


def test_round3_smoke(tmp_path: Path):
    out = run(
        [
            "--corpus-path",
            str(ROOT / "fixtures" / "sample.sqlite"),
            "--window-quality",
            str(ROOT / "fixtures" / "sample_window_quality.csv"),
            "--flags-csv",
            str(ROOT / "task3_multilabel_flags" / "video_multilabel_flags.csv"),
            "--frame-file",
            str(ROOT / "frame.yaml"),
            "--round-yaml",
            str(ROOT / "rounds" / "ROUND-3.yaml"),
            "--out-dir",
            str(tmp_path),
            "--sql-dir",
            str(ROOT / "sql"),
            "--smoke",
        ]
    )
    status = json.loads((tmp_path / "STATUS.json").read_text(encoding="utf-8"))
    assert status["status"] == "smoke_ok"
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["comparison_id"] == "c1_period_drop"
    assert "did" in body
    assert (tmp_path / "metrics" / "did_highsnr_onset.json").is_file()
    assert (tmp_path / "metrics" / "singing_removal.json").is_file()
    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "README.md").is_file()
