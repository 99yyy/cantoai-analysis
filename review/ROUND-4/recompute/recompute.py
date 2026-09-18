#!/usr/bin/env python3
"""Independent ROUND-4 recompute. Does not import src/."""

from __future__ import annotations

import ast
import csv
import glob
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_PATH = REPO_ROOT / "data" / "corpus_v2.sqlite"
FRAME_PATH = REPO_ROOT / "frame.yaml"
MERGE_PATH = REPO_ROOT / "src" / "merge.py"
CONTRACT_PATH = REPO_ROOT / "scripts" / "contract_check.py"
ROUND_YAML_PATH = REPO_ROOT / "rounds" / "ROUND-4.yaml"
COUNT_SQL_PATH = REPO_ROOT / "sql" / "count_windows_ab.sql"
QUALITY_PATH = REPO_ROOT / "task2_window_quality" / "window_quality_with_flags.csv"
FLAGS_PATH = REPO_ROOT / "task3_multilabel_flags" / "video_multilabel_flags.csv"
OUT_PATH = Path(__file__).resolve().parent / "numbers.json"

GATE_PARAM_NAMES = frozenset(
    {
        "enforce_expected",
        "enforce",
        "strict",
        "skip_check",
        "skip_expected",
        "enforce_rows",
    }
)
NAMED_CONTRACT_CHECKS = (
    "merge_pd_merge_once",
    "no_boolean_gate_bypass",
    "review_no_import_src",
    "corpus_sha256_matches_frame",
)
BOILER = "如果覺得內容啱睇嘅subscribe"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def yaml_simple_get(text: str, key: str) -> str | None:
    pat = re.compile(rf"^[ \t]*{re.escape(key)}:[ \t]*(.*)$", re.M)
    m = pat.search(text)
    if m is None:
        return None
    return m.group(1).strip().strip('"').strip("'")


def scalar_int(text: str, key: str) -> int:
    raw = yaml_simple_get(text, key)
    if raw is None:
        raise ValueError(f"missing yaml key {key}")
    return int(raw)


def load_sql_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def pd_merge_counts(source: str) -> tuple[int, int]:
    text_count = source.count("pd.merge(")
    tree = ast.parse(source)
    ast_count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "merge":
            continue
        recv = node.func.value
        if isinstance(recv, ast.Name) and recv.id == "pd":
            ast_count += 1
    return text_count, ast_count


def gate_hits(src_dir: Path) -> list[str]:
    bad: list[str] = []
    for path in sorted(src_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in [*node.args.args, *node.args.kwonlyargs]:
                    if arg.arg in GATE_PARAM_NAMES:
                        bad.append(f"{path.name}:{node.name}:{arg.arg}")
            if isinstance(node, ast.Name) and node.id == "enforce_expected":
                bad.append(f"{path.name}:name:enforce_expected")
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "enforce_expected":
                        bad.append(f"{path.name}:call:enforce_expected")
    return bad


def review_import_src(review_dir: Path) -> list[str]:
    hits: list[str] = []
    if not review_dir.is_dir():
        return hits
    for path in review_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if re.search(r"(?m)^\s*(import src\b|from src\b)", text):
            hits.append(str(path.relative_to(REPO_ROOT)))
    return hits


def csv_ids(path: Path, column: str) -> set[str]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return {row[column] for row in reader if row.get(column)}


def row(
    name: str,
    mine,
    reported,
    reported_source: str,
    command: str,
    match: bool,
) -> dict:
    return {
        "name": name,
        "mine": mine,
        "reported": reported,
        "reported_source": reported_source,
        "command": command,
        "match": match,
    }


def main() -> int:
    if str(REPO_ROOT) in sys.path:
        # Keep this script runnable as `python3 review/ROUND-4/recompute/recompute.py`
        # without ever importing src/.
        pass
    if any(p == "src" or p.endswith("/src") for p in sys.modules):
        raise RuntimeError("src already imported; abort")

    frame_text = FRAME_PATH.read_text(encoding="utf-8")
    round_text = ROUND_YAML_PATH.read_text(encoding="utf-8")
    merge_text = MERGE_PATH.read_text(encoding="utf-8")
    contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
    count_sql_file = re.sub(r"\s+", " ", load_sql_text(COUNT_SQL_PATH).strip().rstrip(";"))
    count_sql_literal = "SELECT COUNT(*) AS n FROM windows WHERE tier IN ('A', 'B')"
    if count_sql_file != count_sql_literal:
        raise ValueError("sql/count_windows_ab.sql does not match recompute literal")

    con = sqlite3.connect(CORPUS_PATH)
    try:
        n_windows_ab = int(con.execute("SELECT COUNT(*) AS n FROM windows WHERE tier IN ('A', 'B')").fetchone()[0])
        n_videos = int(con.execute("SELECT COUNT(*) FROM videos").fetchone()[0])
        n_windows = int(con.execute("SELECT COUNT(*) FROM windows").fetchone()[0])
        n_windows_join_videos = int(
            con.execute(
                "SELECT COUNT(*) FROM windows JOIN videos "
                "ON windows.video_id = videos.video_id"
            ).fetchone()[0]
        )
        n_windows_ab_join_videos = int(
            con.execute(
                "SELECT COUNT(*) FROM windows JOIN videos "
                "ON windows.video_id = videos.video_id "
                "WHERE windows.tier IN ('A', 'B')"
            ).fetchone()[0]
        )
        ab_uids = {
            r[0]
            for r in con.execute(
                "SELECT uid FROM windows WHERE tier IN ('A', 'B')"
            )
        }
        video_ids = {r[0] for r in con.execute("SELECT video_id FROM videos")}
    finally:
        con.close()

    corpus_sha = sha256_file(CORPUS_PATH)
    declared_sha = yaml_simple_get(frame_text, "corpus_sha256")
    declared_rows = scalar_int(frame_text, "expected_rows")
    declared_videos = scalar_int(frame_text, "n_videos")
    wq_expected = int(
        re.search(
            r"windows_quality:\n(?:[ \t].*\n)*?[ \t]+expected_rows: (\d+)",
            frame_text,
        ).group(1)
    )
    vf_expected = int(
        re.search(
            r"video_flags:\n(?:[ \t].*\n)*?[ \t]+expected_rows: (\d+)",
            frame_text,
        ).group(1)
    )
    wv_expected = int(
        re.search(
            r"windows_videos:\n(?:[ \t].*\n)*?[ \t]+expected_rows: (\d+)",
            frame_text,
        ).group(1)
    )

    quality_ids = csv_ids(QUALITY_PATH, "window_id")
    flag_ids = csv_ids(FLAGS_PATH, "video_id")
    n_ab_in_quality = len(ab_uids & quality_ids)
    n_videos_in_flags = len(video_ids & flag_ids)

    metrics_paths = sorted(glob.glob(str(REPO_ROOT / "ROUND-4" / "*" / "metrics" / "*.json")))
    metrics_rel = [str(Path(p).relative_to(REPO_ROOT)) for p in metrics_paths]
    text_count, ast_count = pd_merge_counts(merge_text)
    gates = gate_hits(REPO_ROOT / "src")
    review_hits = review_import_src(REPO_ROOT / "review")
    named = {n: (n in contract_text) for n in NAMED_CONTRACT_CHECKS}
    comparisons_m = len(re.findall(r"^- id:", round_text, flags=re.M))
    if "comparisons: []" in round_text:
        comparisons_m = 0
    expected_m = int(
        (REPO_ROOT / "expected" / "comparisons_m.count").read_text(encoding="utf-8").strip()
    )
    left_attach_uses_spec = (
        "expected_rows = spec[\"expected_rows\"]" in merge_text
        and "return checked_merge(" in merge_text
        and "enforce_expected" not in merge_text
    )

    numbers = [
        row(
            "n_metrics_json",
            len(metrics_rel),
            0,
            "ROUND-4/*/metrics/*.json (absent directory; rounds/ROUND-4.yaml:comparisons is [])",
            "python3 -c \"from pathlib import Path; print(len(list(Path('.').glob('ROUND-4/*/metrics/*.json'))))\"",
            len(metrics_rel) == 0,
        ),
        row(
            "corpus_sha256",
            corpus_sha,
            declared_sha,
            "frame.yaml:inputs.corpus_sha256",
            "python3 -c \"import hashlib; print(hashlib.sha256(open('data/corpus_v2.sqlite','rb').read()).hexdigest())\"",
            corpus_sha == declared_sha,
        ),
        row(
            "expected_rows",
            n_windows_ab,
            declared_rows,
            "frame.yaml:expected_rows via sql/count_windows_ab.sql",
            "python3 -c \"import sqlite3; print(sqlite3.connect('data/corpus_v2.sqlite').execute(open('sql/count_windows_ab.sql').read()).fetchone()[0])\"",
            n_windows_ab == declared_rows,
        ),
        row(
            "n_videos",
            n_videos,
            declared_videos,
            "frame.yaml:video_counts.n_videos",
            "python3 -c \"import sqlite3; print(sqlite3.connect('data/corpus_v2.sqlite').execute('SELECT COUNT(*) FROM videos').fetchone()[0])\"",
            n_videos == declared_videos,
        ),
        row(
            "windows_quality_matched_ab",
            n_ab_in_quality,
            wq_expected,
            "frame.yaml:joins.windows_quality.expected_rows",
            "python3 review/ROUND-4/recompute/recompute.py",
            n_ab_in_quality == wq_expected,
        ),
        row(
            "video_flags_matched",
            n_videos_in_flags,
            vf_expected,
            "frame.yaml:joins.video_flags.expected_rows",
            "python3 review/ROUND-4/recompute/recompute.py",
            n_videos_in_flags == vf_expected,
        ),
        row(
            "windows_ab_join_videos",
            n_windows_ab_join_videos,
            wv_expected,
            "frame.yaml:joins.windows_videos.expected_rows (A+B subset)",
            "python3 -c \"import sqlite3; print(sqlite3.connect('data/corpus_v2.sqlite').execute(\\\"SELECT COUNT(*) FROM windows JOIN videos ON windows.video_id = videos.video_id WHERE windows.tier IN ('A', 'B')\\\").fetchone()[0])\"",
            n_windows_ab_join_videos == wv_expected,
        ),
        row(
            "comparisons_m",
            comparisons_m,
            expected_m,
            "expected/comparisons_m.count and rounds/ROUND-4.yaml:comparisons",
            "python3 -c \"import pathlib; print(pathlib.Path('expected/comparisons_m.count').read_text().strip()); print('comparisons: []' in pathlib.Path('rounds/ROUND-4.yaml').read_text())\"",
            comparisons_m == expected_m == 0,
        ),
        row(
            "pd_merge_text_count",
            text_count,
            1,
            "rounds/ROUND-4.md H2 / tests/test_round4_gates.py PD_MERGE_ONCE",
            "python3 -c \"print(open('src/merge.py').read().count('pd.merge('))\"",
            text_count == 1,
        ),
        row(
            "pd_merge_ast_count",
            ast_count,
            1,
            "rounds/ROUND-4.md H2",
            "python3 review/ROUND-4/recompute/recompute.py",
            ast_count == 1,
        ),
        row(
            "enforce_expected_hits",
            len(gates),
            0,
            "rounds/ROUND-4.md H1 (no boolean gate parameter)",
            "python3 review/ROUND-4/recompute/recompute.py",
            gates == [],
        ),
        row(
            "review_import_src_hits",
            len(review_hits),
            0,
            "rounds/ROUND-4.md H3",
            "python3 review/ROUND-4/recompute/recompute.py",
            review_hits == [],
        ),
        row(
            "left_attach_uses_frame_literal",
            int(left_attach_uses_spec),
            1,
            "src/merge.py left_attach -> checked_merge; expected_rows from spec",
            "python3 -c \"t=open('src/merge.py').read(); print('expected_rows = spec[\\\"expected_rows\\\"]' in t, 'enforce_expected' not in t)\"",
            left_attach_uses_spec,
        ),
    ]

    payload = {
        "metrics_files": metrics_rel,
        "n_windows_total": n_windows,
        "n_windows_join_videos_unfiltered": n_windows_join_videos,
        "gate_hits": gates,
        "review_import_src": review_hits,
        "named_contract_checks_in_contract_check_py": named,
        "boiler_text": BOILER,
        "numbers": numbers,
        "all_match": all(n["match"] for n in numbers),
    }
    tmp = OUT_PATH.with_name(OUT_PATH.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUT_PATH)
    print(json.dumps({"out": str(OUT_PATH.relative_to(REPO_ROOT)), "all_match": payload["all_match"], "n": len(numbers)}, indent=2))
    return 0 if payload["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
