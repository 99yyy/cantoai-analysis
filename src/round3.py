"""ROUND-3 CLI scaffold: load SQL/frame, refuse inference, write STATUS.json.

Does not compute agreement rates, deltas, or other research metrics.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.compare import assert_no_clap_in_comparison, require_comparison_id
from src.frame import load_frame
from src.paths import atomic_write_json, refuse_inference, require_path, sha256_file, write_status
from src.sql_loader import load_sql


COMPARISON_SQL = {
    "c1_period_drop": "c1_period_drop",
    "c2_highsnr_onset_residual": "c2_highsnr_onset",
    "c3_singing_removal": "c3_singing_removal",
}


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
    return parser.parse_args(seq)


def run(argv: list[str] | None = None) -> Path:
    args = parse_args(argv)
    corpus_PATH = require_path("corpus_PATH", args.corpus_PATH)
    window_quality_FILE = require_path("window_quality_FILE", args.window_quality_FILE)
    frame_FILE = require_path("frame_FILE", args.frame_FILE)
    round_yaml_FILE = require_path("round_yaml_FILE", args.round_yaml_FILE)
    out_DIR = require_path("out_DIR", args.out_DIR)
    sql_DIR = require_path("sql_DIR", args.sql_DIR)
    out_DIR.mkdir(parents=True, exist_ok=True)
    status_FILE = out_DIR / "STATUS.json"
    write_status(status_FILE, "running")

    frame = load_frame(str(frame_FILE))
    declared = [c["id"] for c in _comparisons(round_yaml_FILE)]
    for comparison_id, sql_name in COMPARISON_SQL.items():
        require_comparison_id(comparison_id, declared)
        sql_text = load_sql(sql_name, str(sql_DIR))
        columns = _sql_select_names(sql_text)
        assert_no_clap_in_comparison(comparison_id, columns)

    record = {
        "scaffold": True,
        "frame_file": str(frame_FILE),
        "round_yaml": str(round_yaml_FILE),
        "corpus_path": str(corpus_PATH),
        "window_quality": str(window_quality_FILE),
        "comparisons": declared,
        "singing_prob_source": frame.get("singing_prob_source"),
    }
    out_FILE = out_DIR / "scaffold.json"
    atomic_write_json(out_FILE, record)
    write_status(status_FILE, "complete", sha256_file(out_FILE))
    return out_FILE


def _comparisons(round_yaml_FILE: Path) -> list[dict]:
    import yaml

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


def main() -> None:
    run()


if __name__ == "__main__":
    main()
