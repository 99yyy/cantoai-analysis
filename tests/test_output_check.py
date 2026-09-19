"""output_check SQL replay requires a corpus plan and a deterministic statement."""

from __future__ import annotations

import importlib.util
import json
import re
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


def _write_brief(
    root: Path,
    n: str,
    status: str = "open",
    name: str = "n_count",
    n_block: str | None = None,
    frame_block: str | None = None,
    extra_numbers: str = "",
) -> Path:
    md = root / "tasks" / f"TASK-{n}.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"# TASK-{n}\n\nstatus: {status}\n\n"
        f"```numbers\n# name  tol\n{name}  0\n{extra_numbers}```\n"
    )
    if n_block is not None:
        body += f"\n```n\n{n_block}\n```\n"
    if frame_block is not None:
        body += f"\n```frame\n{frame_block}\n```\n"
    md.write_text(body, encoding="utf-8")
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


# --------------------------------------------------------------------------- §4.4


BRIEF_STATUS_FAIL = (
    "needs exactly one line 'status: open', 'status: closed', "
    "'status: escalated' or 'status: blocked'"
)


def _set_brief_status(md: Path, status: str) -> None:
    text = md.read_text(encoding="utf-8")
    md.write_text(
        re.sub(r"^status:[ \t]*\S+[ \t]*$", f"status: {status}", text, count=1, flags=re.M),
        encoding="utf-8",
    )


def _empty_commit(repo: Path, message: str) -> str:
    _git(repo, "commit", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _touch_results(repo: Path, n: str) -> None:
    path = repo / "tasks" / f"TASK-{n}" / "results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[0]["n"] = int(data[0]["n"]) + 1
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_parse_brief_accepts_blocked_and_escalated(tmp_path):
    for st in ("open", "closed", "escalated", "blocked"):
        md = _write_brief(tmp_path, f"s{st}", status=st)
        brief = output_check.parse_brief(md)
        assert brief.status == st
        assert "n_count" in brief.tol
        assert brief.n_decl is None
        assert brief.frame == {}


def test_parse_brief_rejects_uppercase_blocked(tmp_path):
    md = _write_brief(tmp_path, "7", status="BLOCKED")
    with pytest.raises(output_check.Fail, match=BRIEF_STATUS_FAIL):
        output_check.parse_brief(md)


def test_parse_brief_rejects_unknown_and_missing_status(tmp_path):
    md = _write_brief(tmp_path, "7", status="stale")
    with pytest.raises(output_check.Fail, match=BRIEF_STATUS_FAIL):
        output_check.parse_brief(md)
    md.write_text("# TASK-7\n\n```numbers\nn_count  0\n```\n", encoding="utf-8")
    with pytest.raises(output_check.Fail, match=BRIEF_STATUS_FAIL):
        output_check.parse_brief(md)


def test_blocked_status_suspends_iterate_disagreement(conn, tmp_path, capsys):
    md = _iterating_task(tmp_path, "7")
    _set_brief_status(md, "blocked")
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    out = capsys.readouterr().out
    assert fail == []
    assert "TASK-7 [blocked]" in out
    assert "suspended (replay, agreement, and edit-count not run)" in out


def test_escalated_status_suspends_iterate_disagreement(conn, tmp_path, capsys):
    md = _iterating_task(tmp_path, "7")
    _set_brief_status(md, "escalated")
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    out = capsys.readouterr().out
    assert fail == []
    assert "TASK-7 [escalated]" in out
    assert "suspended" in out


def test_open_still_fails_the_same_disagreement(conn, tmp_path):
    md = _iterating_task(tmp_path, "7")
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    assert fail
    assert any("disagree" in m for m in fail)


def test_frozen_blocked_task_notes_suspended(tmp_path, capsys):
    md = _iterating_task(tmp_path, "7")
    _set_brief_status(md, "blocked")
    output_check.frozen_summary(tmp_path, md)
    out = capsys.readouterr().out
    assert "TASK-7 [blocked]: frozen (not touched by this PR)" in out
    assert out.rstrip().endswith("suspended") or "; suspended" in out


def _write_worker_output(repo: Path, n: str = "7") -> None:
    w_sql = repo / "tasks" / f"TASK-{n}" / "sql" / "count_videos.sql"
    w_sql.parent.mkdir(parents=True, exist_ok=True)
    w_sql.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    _write_rows(
        repo / "tasks" / f"TASK-{n}" / "results.json",
        "n_count",
        567,
        f"tasks/TASK-{n}/sql/count_videos.sql",
    )


def _repo_n_result_commits(repo: Path, n_commits: int, n: str = "7") -> None:
    """Brief first, then ``n_commits`` commits that touch results.json."""
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    _write_brief(repo, n)
    _init_git(repo)
    _commit(repo, "brief")
    _write_worker_output(repo, n)
    _commit(repo, "results 1")
    for i in range(2, n_commits + 1):
        _touch_results(repo, n)
        _commit(repo, f"results {i}")


def test_fourth_rewrite_fails_while_open(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_n_result_commits(repo, 4)
    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert any("rewritten 4 times" in line for line in out.splitlines())


def test_escalated_suspends_edit_count_ceiling(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_n_result_commits(repo, 4)
    _set_brief_status(repo / "tasks" / "TASK-7.md", "escalated")
    _commit(repo, "escalate")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "TASK-7 [escalated]" in out
    assert "suspended" in out


def test_reset_commit_restarts_edit_count(tmp_path, capsys):
    """Four rewrites would fail; revising the brief resets the count."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_n_result_commits(repo, 4)

    code_before, _ = _run_main(repo, "--head-ref", "HEAD")
    out_before = capsys.readouterr().out
    assert code_before == 1, out_before
    assert any("rewritten 4 times" in line for line in out_before.splitlines())

    md = repo / "tasks" / "TASK-7.md"
    md.write_text(md.read_text(encoding="utf-8") + "\n<!-- reset -->\n", encoding="utf-8")
    reset = _commit(repo, "reset: revise brief")
    _touch_results(repo, "7")
    _commit(repo, "results after reset")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "output_check: PASS" in out
    got = output_check.commits_touching_since(
        repo, "HEAD", "tasks/TASK-7/results.json", reset
    )
    assert len(got) == 1

def test_blocked_empty_commit_is_recognized(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    _write_brief(repo, "7", status="blocked")
    _init_git(repo)
    _commit(repo, "blocked brief")
    sha = _empty_commit(repo, "BLOCKED: TASK-7 cannot touch scripts/")

    found = output_check.blocked_empty_commits(repo, "HEAD")
    assert len(found) == 1
    assert found[0][0] == sha
    assert found[0][1].startswith("BLOCKED:")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert f"recognized empty commit {sha[:8]} BLOCKED: TASK-7 cannot touch scripts/" in out
    assert "TASK-7 [blocked]" in out
    assert "suspended" in out


def test_blocked_subject_with_file_changes_is_not_the_empty_convention(
    tmp_path, capsys
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    _write_brief(repo, "7", status="blocked")
    _init_git(repo)
    _commit(repo, "blocked brief")
    md = repo / "tasks" / "TASK-7.md"
    md.write_text(md.read_text(encoding="utf-8") + "\n<!-- note -->\n", encoding="utf-8")
    _commit(repo, "BLOCKED: TASK-7 not empty")

    found = output_check.blocked_empty_commits(repo, "HEAD")
    assert found == []
    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "recognized empty commit" not in out


def test_blocked_task_on_main_does_not_fail_the_repo(tmp_path, capsys):
    """Probe class: status: blocked on an iterating task is legal and green."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    _iterating_task(repo, "7")
    _set_brief_status(repo / "tasks" / "TASK-7.md", "blocked")
    _init_git(repo)
    _commit(repo, "TASK-7 blocked")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "suspended" in out
    assert "disagree" not in out


# --------------------------------------------------------------------------- §2.5 + period identity


def _agreeing_videos(
    root: Path,
    n: str = "7",
    row_n: int = 1,
    n_block: str | None = None,
    frame_block: str | None = None,
    extra_numbers: str = "",
    names: tuple[str, ...] = ("n_count",),
) -> Path:
    """Both sides count videos, same value, chosen ``n``."""
    md = _write_brief(
        root,
        n,
        name=names[0],
        n_block=n_block,
        frame_block=frame_block,
        extra_numbers=extra_numbers,
    )
    w_sql = root / "tasks" / f"TASK-{n}" / "sql" / "count_videos.sql"
    v_sql = root / "tasks" / f"TASK-{n}" / "mine_sql" / "count_videos_as.sql"
    w_sql.parent.mkdir(parents=True, exist_ok=True)
    v_sql.parent.mkdir(parents=True, exist_ok=True)
    w_sql.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    v_sql.write_text("SELECT COUNT(*) FROM videos AS vid;\n", encoding="utf-8")
    w_rows = [
        {
            "name": names[0],
            "value": 567,
            "n": row_n,
            "query": f"tasks/TASK-{n}/sql/count_videos.sql",
        }
    ]
    v_rows = [
        {
            "name": names[0],
            "value": 567,
            "n": row_n,
            "query": f"tasks/TASK-{n}/mine_sql/count_videos_as.sql",
        }
    ]
    (root / "tasks" / f"TASK-{n}" / "results.json").write_text(
        json.dumps(w_rows, indent=2) + "\n", encoding="utf-8"
    )
    (root / "tasks" / f"TASK-{n}" / "mine.json").write_text(
        json.dumps(v_rows, indent=2) + "\n", encoding="utf-8"
    )
    return md


def test_parse_brief_task_6_n_and_frame():
    brief = output_check.parse_brief(ROOT / "tasks" / "TASK-6.md")
    assert brief.status == "closed"
    assert len(brief.tol) == 39
    assert brief.n_decl is not None
    assert set(brief.n_decl) == set(brief.tol)
    assert brief.n_decl["n_videos_pre"] == "567"
    assert brief.n_decl["n_match_pre"] == "derived:n_total_pre"
    assert (
        brief.n_decl["gap_contract_pp"]
        == "derived:n_judgeable_pre + n_judgeable_post"
    )
    assert brief.frame[output_check.VIDEOS_EXPECTED] == 567.0
    assert brief.frame[output_check.VIDEOS_EXPECTED_TOL] == 0.0


def test_n_fence_does_not_eat_the_numbers_fence(tmp_path):
    md = _write_brief(tmp_path, "7")
    text = md.read_text(encoding="utf-8")
    assert output_check.N_FENCE.search(text) is None
    assert output_check.BLOCK.search(text) is not None


def test_parse_n_block_rejects_empty(tmp_path):
    md = _write_brief(tmp_path, "7", n_block="# nothing\n")
    with pytest.raises(output_check.Fail, match=r"the n block is empty"):
        output_check.parse_brief(md)


def test_n_block_name_set_must_equal_numbers(tmp_path):
    md = _write_brief(tmp_path, "7", n_block="other  1\n")
    with pytest.raises(output_check.Fail, match=r"```n block"):
        output_check.parse_brief(md)
    md = _write_brief(
        tmp_path, "7", n_block="n_count  1\nother  1\n"
    )
    with pytest.raises(output_check.Fail, match=r"not in the numbers block: other"):
        output_check.parse_brief(md)


def test_parse_n_block_constant_and_derived(tmp_path):
    md = _write_brief(tmp_path, "7", n_block="n_count  derived:n_count\n")
    brief = output_check.parse_brief(md)
    assert brief.n_decl == {"n_count": "derived:n_count"}
    md = _write_brief(tmp_path, "7", n_block="n_count  567\n")
    brief = output_check.parse_brief(md)
    assert brief.n_decl == {"n_count": "567"}


def test_parse_frame_skips_predicates_and_keeps_videos_expected(tmp_path):
    md = _write_brief(
        tmp_path,
        "7",
        frame_block=(
            "windows.tier IN ('A','B')\n"
            "videos_expected 567\n"
            "videos_expected_tol 0\n"
        ),
    )
    brief = output_check.parse_brief(md)
    assert brief.frame == {"videos_expected": 567.0, "videos_expected_tol": 0.0}


def test_without_n_block_matching_n_of_1_still_passes(conn, tmp_path):
    """Declared-n check is off when the brief has no ```n``` fence."""
    md = _agreeing_videos(tmp_path, row_n=1)
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    assert fail == []


def test_with_n_block_n_of_1_fails_even_when_agents_agree(conn, tmp_path):
    """Probe class: both files n=1, pairwise equal, declared n=567 → RED."""
    md = _agreeing_videos(tmp_path, row_n=1, n_block="n_count  567\n")
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    hits = [m for m in fail if "brief declares n=567" in m]
    assert len(hits) == 2
    assert any(m.startswith("results.json:n_count: n=1,") for m in hits)
    assert any(m.startswith("mine.json:n_count: n=1,") for m in hits)
    assert not any("disagree" in m for m in fail)
    assert not any("over the same corpus" in m for m in fail)


def test_pairwise_n_still_fires_alongside_declared_n(conn, tmp_path):
    md = _agreeing_videos(tmp_path, row_n=567, n_block="n_count  567\n")
    mine = tmp_path / "tasks" / "TASK-7" / "mine.json"
    data = json.loads(mine.read_text(encoding="utf-8"))
    data[0]["n"] = 1
    mine.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    assert any("brief declares n=567" in m and m.startswith("mine.json:") for m in fail)
    assert any("worker counted n=567 and verifier n=1" in m for m in fail)


def test_derived_n_uses_replayed_value(conn, tmp_path):
    md = _agreeing_videos(tmp_path, row_n=1, n_block="n_count  derived:n_count\n")
    fail: list[str] = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    assert any("brief declares n=567" in m for m in fail)

    md = _agreeing_videos(tmp_path, row_n=567, n_block="n_count  derived:n_count\n")
    fail = []
    output_check.check_task(tmp_path, md, conn, 60.0, None, None, fail)
    assert fail == []


def test_period_identity_holds_on_replayed_sum():
    fail: list[str] = []
    note = output_check.check_period_identity(
        "6",
        "results.json",
        {
            "n_videos_pre": 0.0,
            "n_videos_post": 0.0,
            "n_unassigned_period": 0.0,
        },
        {
            "n_videos_pre": 391.0,
            "n_videos_post": 176.0,
            "n_unassigned_period": 0.0,
        },
        {"videos_expected": 567.0, "videos_expected_tol": 0.0},
        fail,
    )
    assert fail == []
    assert note is not None
    assert "frame.videos_expected" in note
    assert "567" in note


def test_period_identity_fails_against_frame_field_not_a_literal():
    fail: list[str] = []
    note = output_check.check_period_identity(
        "6",
        "results.json",
        {
            "n_videos_pre": 0.0,
            "n_videos_post": 0.0,
            "n_unassigned_period": 0.0,
        },
        {
            "n_videos_pre": 391.0,
            "n_videos_post": 176.0,
            "n_unassigned_period": 0.0,
        },
        {"videos_expected": 1.0, "videos_expected_tol": 0.0},
        fail,
    )
    assert note is None
    assert fail == [
        "TASK-6: results.json: n_videos_pre + n_videos_post + n_unassigned_period "
        "= 391 + 176 + 0 = 567, but frame.videos_expected is 1 (tol 0)"
    ]


def test_period_identity_skipped_without_videos_expected():
    fail: list[str] = []
    note = output_check.check_period_identity(
        "6",
        "results.json",
        {
            "n_videos_pre": 0.0,
            "n_videos_post": 0.0,
            "n_unassigned_period": 0.0,
        },
        {
            "n_videos_pre": 391.0,
            "n_videos_post": 176.0,
            "n_unassigned_period": 0.0,
        },
        {},
        fail,
    )
    assert note is None
    assert fail == []


def test_period_identity_skipped_when_the_three_names_are_not_declared():
    fail: list[str] = []
    note = output_check.check_period_identity(
        "7",
        "results.json",
        {"n_count": 0.0},
        {"n_count": 567.0},
        {"videos_expected": 567.0},
        fail,
    )
    assert note is None
    assert fail == []


def test_period_identity_source_does_not_hardcode_567():
    src = (ROOT / "scripts" / "output_check.py").read_text(encoding="utf-8")
    start = src.index("def check_period_identity")
    end = src.index("\ndef parse_rows")
    body = src[start:end]
    assert "567" not in body
    assert "VIDEOS_EXPECTED" in body


def test_full_check_task_6_declared_n_and_period_identity(conn, capsys):
    md = ROOT / "tasks" / "TASK-6.md"
    fail: list[str] = []
    output_check.check_task(ROOT, md, conn, 60.0, None, None, fail)
    out = capsys.readouterr().out
    assert fail == []
    assert "39/39 n declared" in out
    assert "period identity" in out
    assert "frame.videos_expected" in out


# --------------------------------------------------------------------------- §2.6 orphan outputs without a matching brief


ORPHAN_BRIEF = (
    "exists but the matching brief tasks/TASK-7.md cannot be found"
)


def test_discover_briefs_is_non_recursive(tmp_path):
    _write_brief(tmp_path, "6")
    archive = tmp_path / "tasks" / "archive"
    archive.mkdir()
    (archive / "TASK-7.md").write_text(
        "# TASK-7\n\nstatus: open\n\n```numbers\nn_count  0\n```\n",
        encoding="utf-8",
    )
    got = output_check.discover_briefs(tmp_path)
    assert [p.name for p in got] == ["TASK-6.md"]


def test_discover_briefs_empty_without_tasks_dir(tmp_path):
    assert output_check.discover_briefs(tmp_path) == []


def test_orphan_output_message_is_stable():
    assert output_check.orphan_output_message("7", "tasks/TASK-7/results.json") == (
        "TASK-7: tasks/TASK-7/results.json exists but the matching brief "
        "tasks/TASK-7.md cannot be found"
    )


def test_orphan_messages_when_results_exist_without_brief(tmp_path):
    _write_worker_output(tmp_path, "7")
    msgs = output_check.orphan_output_messages(tmp_path, [])
    assert msgs == [
        "TASK-7: tasks/TASK-7/results.json exists but the matching brief "
        "tasks/TASK-7.md cannot be found"
    ]


def test_archived_brief_does_not_count_as_matching(tmp_path):
    """Probe class: git mv tasks/TASK-N.md tasks/archive/TASK-N.md, outputs stay."""
    md = _write_brief(tmp_path, "7")
    _write_worker_output(tmp_path, "7")
    archive = tmp_path / "tasks" / "archive"
    archive.mkdir()
    md.rename(archive / "TASK-7.md")
    briefs = output_check.discover_briefs(tmp_path)
    assert briefs == []
    msgs = output_check.orphan_output_messages(tmp_path, briefs)
    assert any(ORPHAN_BRIEF in m for m in msgs)
    assert any("results.json" in m for m in msgs)


def test_matching_top_level_brief_is_not_an_orphan(tmp_path):
    _write_brief(tmp_path, "7")
    _write_worker_output(tmp_path, "7")
    briefs = output_check.discover_briefs(tmp_path)
    assert output_check.orphan_output_messages(tmp_path, briefs) == []


def test_nested_results_under_task_dir_still_need_top_level_brief(tmp_path):
    nested = tmp_path / "tasks" / "archive" / "TASK-7" / "results.json"
    nested.parent.mkdir(parents=True)
    nested.write_text("[]\n", encoding="utf-8")
    msgs = output_check.orphan_output_messages(tmp_path, [])
    assert msgs == [
        "TASK-7: tasks/archive/TASK-7/results.json exists but the matching brief "
        "tasks/TASK-7.md cannot be found"
    ]


def test_results_not_under_task_n_dir_are_not_orphans(tmp_path):
    stray = tmp_path / "tasks" / "misc" / "results.json"
    stray.parent.mkdir(parents=True)
    stray.write_text("[]\n", encoding="utf-8")
    assert output_check.orphan_output_messages(tmp_path, []) == []


def test_no_briefs_and_no_outputs_is_nothing_to_check(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    (repo / "tasks").mkdir()
    _init_git(repo)
    _commit(repo, "empty tasks")
    code, _ = _run_main(repo)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "nothing to check" in out


def test_hide_brief_leave_results_fails_main(tmp_path, capsys):
    """Move/hide the brief, leave results.json → RED (plan §2.6)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    md = _write_brief(repo, "7")
    _write_worker_output(repo, "7")
    archive = repo / "tasks" / "archive"
    archive.mkdir()
    md.rename(archive / "TASK-7.md")
    _init_git(repo)
    _commit(repo, "archived brief, results remain")

    code, _ = _run_main(repo)
    out = capsys.readouterr().out
    assert code == 1, out
    assert ORPHAN_BRIEF in out
    assert "output_check: FAIL" in out
    assert "nothing to check" not in out


def test_hide_brief_then_edit_results_is_red_on_pr(tmp_path, capsys):
    """Measured hole: git mv the brief, then any results.json edit stayed GREEN."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    _write_brief(repo, "7")
    _write_worker_output(repo, "7")
    _init_git(repo)
    base = _commit(repo, "brief and results")

    archive = repo / "tasks" / "archive"
    archive.mkdir()
    (repo / "tasks" / "TASK-7.md").rename(archive / "TASK-7.md")
    _touch_results(repo, "7")
    _commit(repo, "archive brief and edit results")

    code, _ = _run_main(repo, "--base-ref", base, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert ORPHAN_BRIEF in out
    assert "nothing to check" not in out


def test_orphan_outputs_fail_even_when_another_task_is_frozen(tmp_path, capsys):
    """Orphan check is a tree invariant, not skipped by plan §4.1 freeze."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    _write_brief(repo, "6", status="closed")
    _write_brief(repo, "7")
    _write_worker_output(repo, "7")
    _init_git(repo)
    base = _commit(repo, "TASK-6 brief, TASK-7 with outputs")

    archive = repo / "tasks" / "archive"
    archive.mkdir()
    (repo / "tasks" / "TASK-7.md").rename(archive / "TASK-7.md")
    (repo / "LOOP.md").write_text("loop\n", encoding="utf-8")
    _commit(repo, "archive TASK-7 brief; unrelated LOOP.md")

    code, _ = _run_main(repo, "--base-ref", base, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert ORPHAN_BRIEF in out
    assert "TASK-6 [closed]: frozen (not touched by this PR)" in out


def test_both_output_files_without_brief_are_listed(tmp_path):
    _iterating_task(tmp_path, "7")
    (tmp_path / "tasks" / "TASK-7.md").unlink()
    msgs = output_check.orphan_output_messages(tmp_path, [])
    rels = {m.split(": ", 1)[1].split(" exists")[0] for m in msgs}
    assert rels == {
        "tasks/TASK-7/results.json",
        "tasks/TASK-7/mine.json",
    }
