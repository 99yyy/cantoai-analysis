"""Scaffold CLI writes STATUS.json complete without research metrics."""

from __future__ import annotations

import json
from pathlib import Path

from src.round3 import run

ROOT = Path(__file__).resolve().parents[1]


def test_round3_scaffold(tmp_path: Path):
    out = run(
        [
            "--corpus-path",
            str(ROOT / "fixtures" / "schema.sqlite"),
            "--window-quality",
            str(ROOT / "fixtures" / "sample_window_quality.csv"),
            "--frame-file",
            str(ROOT / "frame.yaml"),
            "--round-yaml",
            str(ROOT / "rounds" / "ROUND-3.yaml"),
            "--out-dir",
            str(tmp_path),
            "--sql-dir",
            str(ROOT / "sql"),
        ]
    )
    status = json.loads((tmp_path / "STATUS.json").read_text(encoding="utf-8"))
    assert status["status"] == "complete"
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["scaffold"] is True
    assert "did" not in body
    assert "agreement" not in body
    text = out.read_text(encoding="utf-8")
    assert "pp" not in text
