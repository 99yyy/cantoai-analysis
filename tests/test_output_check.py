"""output_check SQL replay requires a corpus plan and a deterministic statement."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "output_check", ROOT / "scripts" / "output_check.py"
)
assert SPEC is not None and SPEC.loader is not None
output_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(output_check)

CORPUS_PATH = ROOT / "data" / "corpus_v2.sqlite"
N_VIDEOS_PRE_SQL = ROOT / "tasks" / "TASK-6" / "sql" / "n_videos_pre.sql"
PLAN_FAIL = r"EXPLAIN QUERY PLAN does not SCAN or SEARCH a corpus table"


@pytest.fixture
def conn():
    c = sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True)
    try:
        yield c
    finally:
        c.close()


def _run(conn: sqlite3.Connection, tmp_path: Path, sql: str, name: str = "probe.sql") -> float:
    path = tmp_path / name
    path.write_text(sql, encoding="utf-8")
    return output_check.run_sql(conn, f"results.json:{path.stem}", path, 60.0)


def test_constant_select_fails_corpus_plan_gate(conn, tmp_path):
    with pytest.raises(output_check.Fail, match=PLAN_FAIL):
        _run(conn, tmp_path, "SELECT 12345;\n", name="n_videos_pre.sql")


def test_arithmetic_constant_select_fails_corpus_plan_gate(conn, tmp_path):
    with pytest.raises(output_check.Fail, match=PLAN_FAIL):
        _run(conn, tmp_path, "SELECT 12000 + 345;\n", name="count_videos_pre.sql")


def test_sqlite_master_scan_is_not_a_corpus_touch(conn, tmp_path):
    with pytest.raises(output_check.Fail, match=PLAN_FAIL):
        _run(conn, tmp_path, "SELECT COUNT(*) FROM sqlite_master;\n")


def test_constant_cte_is_not_a_corpus_touch(conn, tmp_path):
    with pytest.raises(output_check.Fail, match=PLAN_FAIL):
        _run(conn, tmp_path, "WITH x AS (SELECT 1 AS a) SELECT a FROM x;\n")


def test_cte_named_after_a_corpus_table_is_not_a_touch(conn, tmp_path):
    with pytest.raises(output_check.Fail, match=PLAN_FAIL):
        _run(conn, tmp_path, "WITH videos AS (SELECT 12345 AS c) SELECT c FROM videos;\n")


def test_count_from_videos_passes_corpus_plan_gate(conn, tmp_path):
    got = _run(conn, tmp_path, "SELECT COUNT(*) FROM videos;\n")
    assert got == 567.0


def test_aliased_videos_scan_passes_corpus_plan_gate(conn):
    got = output_check.run_sql(conn, "results.json:n_videos_pre", N_VIDEOS_PRE_SQL, 60.0)
    assert got == 391.0


def _parse(tmp_path: Path, rows: list[dict], names: list[str]) -> tuple[dict | None, list[str]]:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    fail: list[str] = []
    got = output_check.parse_rows(
        path, {n: 0.0 for n in names}, fail, "6", ROOT
    )
    return got, fail


def test_duplicate_query_string_still_fails(tmp_path):
    q = "tasks/TASK-6/sql/n_videos_pre.sql"
    got, fail = _parse(
        tmp_path,
        [
            {"name": "a", "value": 1, "n": 1, "query": q},
            {"name": "b", "value": 2, "n": 1, "query": q},
        ],
        ["a", "b"],
    )
    assert got is None
    assert any("already backs a" in m and "one route may produce only one number" in m for m in fail)


def test_path_alias_is_the_same_sql_route(tmp_path):
    got, fail = _parse(
        tmp_path,
        [
            {
                "name": "a",
                "value": 1,
                "n": 1,
                "query": "tasks/TASK-6/sql/n_videos_pre.sql",
            },
            {
                "name": "b",
                "value": 2,
                "n": 1,
                "query": "tasks/TASK-6/sql/../sql/n_videos_pre.sql",
            },
        ],
        ["a", "b"],
    )
    assert got is None
    assert any(
        "query 'tasks/TASK-6/sql/../sql/n_videos_pre.sql' already backs a" in m
        and "one route may produce only one number" in m
        for m in fail
    )


def test_dot_segment_path_alias_is_the_same_sql_route(tmp_path):
    got, fail = _parse(
        tmp_path,
        [
            {
                "name": "a",
                "value": 1,
                "n": 1,
                "query": "tasks/TASK-6/sql/n_videos_pre.sql",
            },
            {
                "name": "b",
                "value": 2,
                "n": 1,
                "query": "tasks/TASK-6/sql/./n_videos_pre.sql",
            },
        ],
        ["a", "b"],
    )
    assert got is None
    assert any("already backs a" in m for m in fail)


def test_distinct_sql_files_are_not_duplicate_routes(tmp_path):
    got, fail = _parse(
        tmp_path,
        [
            {
                "name": "a",
                "value": 1,
                "n": 1,
                "query": "tasks/TASK-6/sql/n_videos_pre.sql",
            },
            {
                "name": "b",
                "value": 2,
                "n": 1,
                "query": "tasks/TASK-6/sql/n_videos_post.sql",
            },
        ],
        ["a", "b"],
    )
    assert got is not None
    assert fail == []


def test_statement_sha256_strips_comments_and_outer_whitespace():
    a = output_check.statement_sha256("SELECT COUNT(*) FROM videos;\n")
    b = output_check.statement_sha256(
        "-- copied from worker\nSELECT COUNT(*) FROM videos;  /* trailing */\n"
    )
    c = output_check.statement_sha256("\n  SELECT COUNT(*) FROM videos  \n")
    assert a == b == c
    assert len(a) == 64


def test_statement_sha256_differs_for_distinct_sql():
    a = output_check.statement_sha256("SELECT COUNT(*) FROM videos;\n")
    b = output_check.statement_sha256("SELECT COUNT(*) FROM videos AS vid;\n")
    assert a != b


def test_cross_side_identical_statement_is_a_collision(tmp_path):
    w = tmp_path / "sql" / "n_videos_pre.sql"
    v = tmp_path / "mine_sql" / "count_videos_pre.sql"
    w.parent.mkdir()
    v.parent.mkdir()
    w.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    v.write_text(
        "-- verifier copy\nSELECT COUNT(*) FROM videos;\n", encoding="utf-8"
    )
    h = output_check.statement_sha256("SELECT COUNT(*) FROM videos;\n")
    msgs = output_check.cross_side_sql_hash_collisions(
        "6", tmp_path, {w: "n_videos_pre"}, {v: "n_videos_pre"}
    )
    assert len(msgs) == 1
    assert (
        f"TASK-6: sql/n_videos_pre.sql backs n_videos_pre in results.json and "
        f"mine_sql/count_videos_pre.sql backs n_videos_pre in mine.json; "
        f"statement sha256 {h} after strip_and_split; "
        f"the second computation must be its own"
    ) == msgs[0]


def test_cross_side_distinct_statements_are_not_collisions(tmp_path):
    w = tmp_path / "sql" / "n_videos_pre.sql"
    v = tmp_path / "mine_sql" / "count_videos_pre.sql"
    w.parent.mkdir()
    v.parent.mkdir()
    w.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    v.write_text("SELECT COUNT(*) FROM videos AS vid;\n", encoding="utf-8")
    msgs = output_check.cross_side_sql_hash_collisions(
        "6", tmp_path, {w: "n_videos_pre"}, {v: "n_videos_pre"}
    )
    assert msgs == []


def test_same_path_on_both_sides_is_not_a_hash_collision(tmp_path):
    p = tmp_path / "sql" / "shared.sql"
    p.parent.mkdir()
    p.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    msgs = output_check.cross_side_sql_hash_collisions(
        "6", tmp_path, {p: "a"}, {p: "a"}
    )
    assert msgs == []


DETERMINISM = r"a replayed number must be deterministic"


def test_forbidden_nondeterminism_names_random_and_randomblob():
    assert (
        output_check.forbidden_nondeterminism(
            "SELECT COUNT(*) + (abs(random()) % 5) / 100.0 FROM videos"
        )
        == "random()"
    )
    assert (
        output_check.forbidden_nondeterminism(
            "SELECT COUNT(*) + length(randomblob(4)) FROM videos"
        )
        == "randomblob()"
    )


def test_forbidden_nondeterminism_strftime_now_family():
    assert (
        output_check.forbidden_nondeterminism(
            "SELECT COUNT(*) + CAST(strftime('%f', 'now') AS REAL) FROM videos"
        )
        == "strftime('now')"
    )
    assert (
        output_check.forbidden_nondeterminism(
            "SELECT COUNT(*) FROM videos WHERE date('now') IS NOT NULL"
        )
        == "strftime('now')"
    )
    assert (
        output_check.forbidden_nondeterminism(
            "SELECT COUNT(*) FROM videos WHERE datetime('now', 'localtime') IS NOT NULL"
        )
        == "strftime('now')"
    )
    assert (
        output_check.forbidden_nondeterminism(
            "SELECT COUNT(*) FROM videos WHERE CURRENT_TIMESTAMP IS NOT NULL"
        )
        == "strftime('now')"
    )


def test_forbidden_nondeterminism_allows_strftime_without_now():
    assert (
        output_check.forbidden_nondeterminism(
            "SELECT COUNT(*) FROM videos WHERE strftime('%Y', '2024-01-01') = '2024'"
        )
        is None
    )


def test_random_jitter_fails_determinism_gate(conn, tmp_path):
    with pytest.raises(output_check.Fail, match=DETERMINISM):
        _run(
            conn,
            tmp_path,
            "SELECT COUNT(*) + (abs(random()) % 5) / 100.0 FROM videos;\n",
            name="gap_all_pp.sql",
        )


def test_randomblob_fails_determinism_gate(conn, tmp_path):
    with pytest.raises(output_check.Fail, match=r"uses randomblob\(\)"):
        _run(
            conn,
            tmp_path,
            "SELECT COUNT(*) + length(randomblob(4)) FROM videos;\n",
        )


def test_strftime_now_fails_determinism_gate(conn, tmp_path):
    with pytest.raises(output_check.Fail, match=r"strftime\('now'\)"):
        _run(
            conn,
            tmp_path,
            "SELECT COUNT(*) + CAST(strftime('%f', 'now') AS REAL) / 1000 FROM videos;\n",
        )


def test_random_in_comment_is_not_a_call(conn, tmp_path):
    got = _run(
        conn,
        tmp_path,
        "SELECT COUNT(*) FROM videos; -- random() strftime('now')\n",
    )
    assert got == 567.0


def test_execute_twice_disagreement_fails(conn, tmp_path):
    state = {"n": 0}

    def flip() -> int:
        state["n"] += 1
        return state["n"]

    conn.create_function("flip", 0, flip)
    with pytest.raises(output_check.Fail, match=r"returned 568 then 569"):
        _run(conn, tmp_path, "SELECT COUNT(*) + flip() FROM videos;\n")
