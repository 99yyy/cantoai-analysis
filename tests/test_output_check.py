"""output_check SQL replay requires a corpus plan and a deterministic statement."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
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


# --------------------------------------------------------------------------- §4.1


CORPUS_SHA = "2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f"


def test_task_ids_from_paths_brief_and_either_output():
    assert output_check.task_ids_from_paths(["tasks/TASK-7.md"]) == frozenset({"7"})
    assert output_check.task_ids_from_paths(["tasks/TASK-7/results.json"]) == frozenset(
        {"7"}
    )
    assert output_check.task_ids_from_paths(["tasks/TASK-7/mine.json"]) == frozenset({"7"})
    assert output_check.task_ids_from_paths(
        ["tasks/TASK-8/sql/n.sql", "tasks/TASK-8/mine_sql/n.sql"]
    ) == frozenset({"8"})
    both = output_check.task_ids_from_paths(
        ["tasks/TASK-7/results.json", "LOOP.md", "tasks/TASK-8.md"]
    )
    assert both == frozenset({"7", "8"})


def test_task_ids_from_paths_ignores_review_and_unrelated():
    assert output_check.task_ids_from_paths(
        ["review/TASK-7/audit.md", "scripts/output_check.py", "tasks/NOTES.md"]
    ) == frozenset()
    assert output_check.task_ids_from_paths(
        ["tasks/TASK-6/open_analysis.md"]
    ) == frozenset({"6"})
    assert output_check.task_ids_from_paths([]) == frozenset()
    assert output_check.task_ids_from_paths(["src/frame.py"]) == frozenset()


def _write_brief(root: Path, n: str, status: str = "open", name: str = "n_count") -> Path:
    md = root / "tasks" / f"TASK-{n}.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        f"# TASK-{n}\n\nstatus: {status}\n\n"
        f"```numbers\n# name  tol\n{name}  0\n```\n",
        encoding="utf-8",
    )
    return md


def _write_rows(path: Path, name: str, value: float, query: str, n: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [{"name": name, "value": value, "n": n, "query": query}],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _iterating_task(root: Path, n: str = "7") -> Path:
    """Open task with both outputs present and a real disagreement."""
    md = _write_brief(root, n)
    w_sql = root / "tasks" / f"TASK-{n}" / "sql" / "count_videos.sql"
    v_sql = root / "tasks" / f"TASK-{n}" / "mine_sql" / "count_windows.sql"
    w_sql.parent.mkdir(parents=True, exist_ok=True)
    v_sql.parent.mkdir(parents=True, exist_ok=True)
    w_sql.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    v_sql.write_text("SELECT COUNT(*) FROM windows AS w;\n", encoding="utf-8")
    _write_rows(
        root / "tasks" / f"TASK-{n}" / "results.json",
        "n_count",
        567,
        f"tasks/TASK-{n}/sql/count_videos.sql",
    )
    _write_rows(
        root / "tasks" / f"TASK-{n}" / "mine.json",
        "n_count",
        4911,
        f"tasks/TASK-{n}/mine_sql/count_windows.sql",
    )
    return md


def test_check_task_fails_open_iterate_disagreement(conn, tmp_path):
    md = _iterating_task(tmp_path, "7")
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    assert fail, "full check must fail an iterating disagreement"
    assert any("disagree" in m for m in fail)


def test_frozen_summary_does_not_fail_open_iterate_disagreement(tmp_path, capsys):
    md = _iterating_task(tmp_path, "7")
    output_check.frozen_summary(tmp_path, md)
    out = capsys.readouterr().out
    assert "TASK-7 [open]: frozen (not touched by this PR)" in out
    assert "results.json, mine.json" in out


def test_frozen_summary_open_task_does_not_fail_unrelated_pr(conn, tmp_path):
    """An open iterating task must not redden a PR that does not touch it."""
    md = _iterating_task(tmp_path, "7")
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    assert fail
    # frozen path is what main() uses when the id is absent from the PR diff
    output_check.frozen_summary(tmp_path, md)
    # check_task's fail list is unchanged by frozen_summary (it has no fail arg)
    assert output_check.task_ids_from_paths(
        ["scripts/output_check.py", "LOOP.md"]
    ) == frozenset()


def test_full_check_task_6_closed_still_agrees(conn):
    """PR-scoped skip must not be the only path that still sees TASK-6."""
    md = ROOT / "tasks" / "TASK-6.md"
    fail: list[str] = []
    output_check.check_task(ROOT, md, conn, 60.0, None, None, fail)
    assert fail == []


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _init_git(repo: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "probe@example.com")
    _git(repo, "config", "user.name", "probe")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _run_main(repo: Path, *extra: str) -> tuple[int, str]:
    argv = [
        "output_check.py",
        "--repo-root",
        str(repo),
        "--corpus",
        str(CORPUS_PATH),
        *extra,
    ]
    old = sys.argv
    sys.argv = argv
    try:
        code = output_check.main()
    finally:
        sys.argv = old
    return code, ""


def test_unrelated_pr_is_green_while_open_task_iterates(tmp_path, capsys):
    """Probe: TASK-7 in ITERATE on the tree; the PR only adds TASK-8 worker.

    After (§4.1): GREEN. The same tree fully checked (no base ref) is RED.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    _iterating_task(repo, "7")
    _write_brief(repo, "8")
    _init_git(repo)
    base = _commit(repo, "main: TASK-7 iterating, TASK-8 brief")

    w_sql = repo / "tasks" / "TASK-8" / "sql" / "count_videos.sql"
    w_sql.parent.mkdir(parents=True, exist_ok=True)
    w_sql.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    _write_rows(
        repo / "tasks" / "TASK-8" / "results.json",
        "n_count",
        567,
        "tasks/TASK-8/sql/count_videos.sql",
    )
    _commit(repo, "TASK-8 worker")

    code, _ = _run_main(repo, "--base-ref", base, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "full-check TASK-8" in out
    assert "TASK-7 [open]: frozen (not touched by this PR)" in out
    assert "output_check: PASS" in out

    code_all, _ = _run_main(repo)
    out_all = capsys.readouterr().out
    assert code_all == 1, out_all
    assert any("disagree" in line for line in out_all.splitlines())


def test_pr_that_touches_either_output_still_compares(tmp_path, capsys):
    """Plan §4.3: editing mine.json on an iterating task re-runs the comparison."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    _iterating_task(repo, "7")
    _init_git(repo)
    base = _commit(repo, "main: TASK-7 iterating")

    mine = repo / "tasks" / "TASK-7" / "mine.json"
    data = json.loads(mine.read_text(encoding="utf-8"))
    data[0]["n"] = 2
    mine.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _commit(repo, "retry mine.json")

    code, _ = _run_main(repo, "--base-ref", base, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert "full-check TASK-7" in out
    assert any("disagree" in line for line in out.splitlines())
