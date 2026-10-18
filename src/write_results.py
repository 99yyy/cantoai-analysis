from __future__ import annotations

import argparse
import ast
import json
import sqlite3
from pathlib import Path

from src.hashing import verify_corpus_hash
from src.pins import load_frame_counts

SQL_NAMES = [
    "n_videos_pre",
    "n_videos_post",
    "n_unassigned_period",
    "n_unassigned_film",
    "n_total_pre",
    "n_total_post",
    "n_match_pre",
    "n_match_post",
    "n_empty_realized_pre",
    "n_empty_realized_post",
    "n_dur_le_0_pre",
    "n_dur_le_0_post",
    "n_empty_and_zerodur_pre",
    "n_empty_and_zerodur_post",
    "n_judgeable_film_pre",
    "n_judgeable_film_post",
    "n_judgeable_other_pre",
    "n_judgeable_other_post",
    "gap_all_pp",
    "gap_excl_none_pp",
    "gap_excl_zerodur_pp",
    "agree_film_pre",
    "agree_film_post",
    "agree_other_pre",
    "agree_other_post",
    "rare_share_pre",
    "rare_share_post",
    "rate_tone_pre_pm",
    "rate_tone_post_pm",
    "rate_segment_pre_pm",
    "rate_segment_post_pm",
    "rate_diff_pre_pm",
    "rate_diff_post_pm",
    "rate_none_pre_pm",
    "rate_none_post_pm",
]

DERIVED = {
    "n_judgeable_pre": "n_total_pre - n_empty_realized_pre - n_dur_le_0_pre + n_empty_and_zerodur_pre",
    "n_judgeable_post": "n_total_post - n_empty_realized_post - n_dur_le_0_post + n_empty_and_zerodur_post",
    "gap_contract_pp": "100 * (n_match_pre / n_judgeable_pre - n_match_post / n_judgeable_post)",
    "did_film_pp": "100 * ((agree_film_pre - agree_film_post) - (agree_other_pre - agree_other_post))",
}

ORDER = [
    "n_videos_pre",
    "n_videos_post",
    "n_unassigned_period",
    "n_unassigned_film",
    "n_total_pre",
    "n_total_post",
    "n_match_pre",
    "n_match_post",
    "n_empty_realized_pre",
    "n_empty_realized_post",
    "n_dur_le_0_pre",
    "n_dur_le_0_post",
    "n_empty_and_zerodur_pre",
    "n_empty_and_zerodur_post",
    "n_judgeable_pre",
    "n_judgeable_post",
    "n_judgeable_film_pre",
    "n_judgeable_film_post",
    "n_judgeable_other_pre",
    "n_judgeable_other_post",
    "gap_contract_pp",
    "gap_all_pp",
    "gap_excl_none_pp",
    "gap_excl_zerodur_pp",
    "agree_film_pre",
    "agree_film_post",
    "agree_other_pre",
    "agree_other_post",
    "did_film_pp",
    "rare_share_pre",
    "rare_share_post",
    "rate_tone_pre_pm",
    "rate_tone_post_pm",
    "rate_segment_pre_pm",
    "rate_segment_post_pm",
    "rate_diff_pre_pm",
    "rate_diff_post_pm",
    "rate_none_pre_pm",
    "rate_none_post_pm",
]


def run_sql_file(conn: sqlite3.Connection, sql_FILE: str) -> float:
    text = Path(sql_FILE).read_text(encoding="utf-8")
    cur = conn.execute(text)
    rows = cur.fetchall()
    value = rows[0][0] if len(rows) == 1 and len(rows[0]) == 1 else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("sql file did not return exactly one number")
    return float(value)


def eval_derived(expr: str, known: dict[str, float]) -> float:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError("derived expression contains a disallowed character") from None

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in known:
                raise ValueError("derived expression contains a disallowed character")
            return known[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = ev(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            return left / right
        raise ValueError("derived expression contains a disallowed character")

    return ev(tree.body)


N_FOR: dict[str, tuple[str, ...]] = {
    "n_videos_pre": ("videos",),
    "n_videos_post": ("videos",),
    "n_unassigned_period": ("videos",),
    "n_unassigned_film": ("videos",),
    "n_total_pre": ("n_total_pre",),
    "n_total_post": ("n_total_post",),
    "n_match_pre": ("n_total_pre",),
    "n_match_post": ("n_total_post",),
    "n_empty_realized_pre": ("n_total_pre",),
    "n_empty_realized_post": ("n_total_post",),
    "n_dur_le_0_pre": ("n_total_pre",),
    "n_dur_le_0_post": ("n_total_post",),
    "n_empty_and_zerodur_pre": ("n_total_pre",),
    "n_empty_and_zerodur_post": ("n_total_post",),
    "n_judgeable_pre": ("n_total_pre",),
    "n_judgeable_post": ("n_total_post",),
    "n_judgeable_film_pre": ("n_total_pre",),
    "n_judgeable_film_post": ("n_total_post",),
    "n_judgeable_other_pre": ("n_total_pre",),
    "n_judgeable_other_post": ("n_total_post",),
    "gap_contract_pp": ("n_judgeable_pre", "n_judgeable_post"),
    "gap_all_pp": ("n_total_pre", "n_total_post"),
    "gap_excl_none_pp": ("n_total_pre", "n_total_post"),
    "gap_excl_zerodur_pp": ("n_total_pre", "n_total_post"),
    "agree_film_pre": ("n_judgeable_film_pre",),
    "agree_film_post": ("n_judgeable_film_post",),
    "agree_other_pre": ("n_judgeable_other_pre",),
    "agree_other_post": ("n_judgeable_other_post",),
    "did_film_pp": (
        "n_judgeable_film_pre",
        "n_judgeable_film_post",
        "n_judgeable_other_pre",
        "n_judgeable_other_post",
    ),
    "rare_share_pre": ("n_total_pre",),
    "rare_share_post": ("n_total_post",),
    "rate_tone_pre_pm": ("n_total_pre",),
    "rate_tone_post_pm": ("n_total_post",),
    "rate_segment_pre_pm": ("n_total_pre",),
    "rate_segment_post_pm": ("n_total_post",),
    "rate_diff_pre_pm": ("n_total_pre",),
    "rate_diff_post_pm": ("n_total_post",),
    "rate_none_pre_pm": ("n_total_pre",),
    "rate_none_post_pm": ("n_total_post",),
}


def n_for(name: str, got: dict[str, float], videos_n: int) -> int:
    parts = N_FOR.get(name)
    if parts is None:
        raise ValueError("n_for received an undeclared number name")
    if parts == ("videos",):
        return videos_n
    return int(sum(got[part] for part in parts))


def json_num(name: str, value: float) -> int | float:
    if name.startswith("n_"):
        return int(round(value))
    return float(value)


def query_for(name: str) -> str:
    if name in DERIVED:
        return "derived:" + DERIVED[name]
    return f"tasks/TASK-6/sql/{name}.sql"


def compute_results(
    corpus_PATH: str, readme_PATH: str, brief_PATH: str, sql_DIR: str
) -> list[dict]:
    verify_corpus_hash(corpus_PATH, readme_PATH)
    videos_n = load_frame_counts(brief_PATH, readme_PATH).videos_expected
    conn = sqlite3.connect("file:" + corpus_PATH + "?mode=ro", uri=True)
    try:
        got: dict[str, float] = {}
        for name in SQL_NAMES:
            sql_FILE = str(Path(sql_DIR) / (name + ".sql"))
            got[name] = run_sql_file(conn, sql_FILE)
        for name, expr in DERIVED.items():
            got[name] = eval_derived(expr, got)
    finally:
        conn.close()
    rows = []
    for name in ORDER:
        rows.append(
            {
                "name": name,
                "value": json_num(name, got[name]),
                "n": n_for(name, got, videos_n),
                "query": query_for(name),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_PATH", required=True)
    parser.add_argument("--readme_PATH", required=True)
    parser.add_argument("--brief_PATH", required=True)
    parser.add_argument("--sql_DIR", required=True)
    parser.add_argument("--out_FILE", required=True)
    args = parser.parse_args()
    rows = compute_results(
        args.corpus_PATH, args.readme_PATH, args.brief_PATH, args.sql_DIR
    )
    out_FILE = args.out_FILE
    tmp_FILE = out_FILE + ".tmp"
    Path(tmp_FILE).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    Path(tmp_FILE).replace(Path(out_FILE))


if __name__ == "__main__":
    main()
