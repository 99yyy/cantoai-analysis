"""RESULT.json: auditor round outcome; subtype is machine, verdict is research.

Probe class: a RESULT claiming subtype out_of_turns while the post-reset
rewrite count is below cap must go red. The same tree is green on the
main checker (no RESULT gate). That before/after is recorded in the PR
body; this file keeps the after (must-fail) half so the gate cannot
regress without a red test.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tests.test_output_check import (
    CORPUS_PATH,
    CORPUS_SHA,
    ROOT,
    _agreeing_videos,
    _commit,
    _init_git,
    _run_main,
    _set_brief_status,
    _set_corpus_sha,
    _touch_results,
    _write_brief,
    _write_rows,
    output_check,
)

FIXTURE = ROOT / "tests" / "fixtures" / "result_probe" / "RESULT.json"
OUT_OF_TURNS_BELOW_CAP = (
    "RESULT.json subtype is out_of_turns but rewrite count is 1 (cap is 3)"
)
TASK6_RESULT = ROOT / "tasks" / "TASK-6" / "RESULT.json"


@pytest.fixture
def conn():
    c = sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True)
    try:
        yield c
    finally:
        c.close()


def _write_result(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _base_payload(
    n: str = "7",
    subtype: str = "success",
    verdict: str | None = "refuted",
    **overrides: object,
) -> dict:
    body: dict = {
        "task": f"TASK-{n}",
        "subtype": subtype,
        "verdict": verdict,
        "hypothesis": "Agreement falls after 2025.",
        "why": "gap_all_pp is 7.1.",
        "numbers": {"n_count": {"value": 567.0, "within_tol": True}},
        "turns_used": 2,
        "turn_cap": 3,
        "corpus_sha": CORPUS_SHA,
        "forked_from": None,
        "fork_depth": 0,
    }
    body.update(overrides)
    return body


def _write_agreeing_pair(root: Path, n: str = "7") -> None:
    """Worker + verifier videos-count; does not touch the brief."""
    w_sql = root / "tasks" / f"TASK-{n}" / "sql" / "count_videos.sql"
    v_sql = root / "tasks" / f"TASK-{n}" / "mine_sql" / "count_videos_as.sql"
    w_sql.parent.mkdir(parents=True, exist_ok=True)
    v_sql.parent.mkdir(parents=True, exist_ok=True)
    w_sql.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    v_sql.write_text("SELECT COUNT(*) FROM videos AS vid;\n", encoding="utf-8")
    _write_rows(
        root / "tasks" / f"TASK-{n}" / "results.json",
        "n_count",
        567,
        f"tasks/TASK-{n}/sql/count_videos.sql",
    )
    _write_rows(
        root / "tasks" / f"TASK-{n}" / "mine.json",
        "n_count",
        567,
        f"tasks/TASK-{n}/mine_sql/count_videos_as.sql",
    )


def _closed_agreeing(root: Path, n: str = "7") -> Path:
    md = _agreeing_videos(root, n)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    return md


def test_fixture_claims_out_of_turns_with_null_verdict():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["subtype"] == "out_of_turns"
    assert data["verdict"] is None
    assert data["turn_cap"] == 3
    assert "cost_usd" not in data
    assert "budget_usd" not in data
    assert "val_iterations" not in data


def test_task_6_has_no_result_and_full_check_still_agrees(conn):
    """Transitional: TASK-6 closed before RESULT.json; do not invent a verdict."""
    assert not TASK6_RESULT.is_file()
    md = ROOT / "tasks" / "TASK-6.md"
    fail: list[str] = []
    output_check.check_task(ROOT, md, conn, 60.0, None, None, fail, CORPUS_SHA)
    assert fail == []


def test_parse_result_success_refuted(tmp_path):
    path = tmp_path / "RESULT.json"
    _write_result(path, _base_payload())
    got = output_check.parse_result(path, "7", {"n_count": 0.0}, CORPUS_SHA)
    assert got["subtype"] == "success"
    assert got["verdict"] == "refuted"


def test_parse_result_rejects_dollar_and_val_iteration_fields(tmp_path):
    path = tmp_path / "RESULT.json"
    payload = _base_payload(cost_usd=1.0, budget_usd=2.0, val_iterations=4)
    _write_result(path, payload)
    with pytest.raises(
        output_check.Fail,
        match=r"must not include cost_usd, budget_usd, val_iterations",
    ):
        output_check.parse_result(path, "7", {"n_count": 0.0}, CORPUS_SHA)


def test_parse_result_verdict_null_unless_success(tmp_path):
    path = tmp_path / "RESULT.json"
    _write_result(
        path,
        _base_payload(subtype="blocked", verdict="refuted"),
    )
    with pytest.raises(
        output_check.Fail,
        match=r"verdict must be null unless subtype is success",
    ):
        output_check.parse_result(path, "7", {"n_count": 0.0}, CORPUS_SHA)


def test_parse_result_success_requires_research_verdict(tmp_path):
    path = tmp_path / "RESULT.json"
    _write_result(path, _base_payload(subtype="success", verdict=None))
    with pytest.raises(
        output_check.Fail,
        match=r"verdict must be one of",
    ):
        output_check.parse_result(path, "7", {"n_count": 0.0}, CORPUS_SHA)


def test_parse_result_turn_cap_is_three(tmp_path):
    path = tmp_path / "RESULT.json"
    _write_result(path, _base_payload(turn_cap=16))
    with pytest.raises(
        output_check.Fail,
        match=r"turn_cap must be 3",
    ):
        output_check.parse_result(path, "7", {"n_count": 0.0}, CORPUS_SHA)


def test_parse_result_corpus_sha_must_match_readme_pin(tmp_path):
    path = tmp_path / "RESULT.json"
    wrong = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    _write_result(path, _base_payload(corpus_sha=wrong))
    with pytest.raises(
        output_check.Fail,
        match=r"corpus_sha is a{64}, README pin is",
    ):
        output_check.parse_result(path, "7", {"n_count": 0.0}, CORPUS_SHA)


def test_parse_result_why_must_contain_a_number(tmp_path):
    path = tmp_path / "RESULT.json"
    _write_result(path, _base_payload(why="the gap remains."))
    with pytest.raises(
        output_check.Fail,
        match=r"why must contain a number",
    ):
        output_check.parse_result(path, "7", {"n_count": 0.0}, CORPUS_SHA)


def test_success_result_on_agreeing_closed_task_passes(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert fail == []


def test_success_does_not_mean_hypothesis_supported(conn, tmp_path):
    """subtype success + verdict refuted is a legal pair."""
    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(verdict="refuted"),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert fail == []


def test_success_without_verifier_fails(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    (tmp_path / "tasks" / "TASK-7" / "mine.json").unlink()
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any("subtype is success but mine.json is missing" in m for m in fail)


def test_result_on_open_task_fails(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(
        "RESULT.json is present but status is open" in m for m in fail
    )


def test_blocked_result_requires_blocked_status(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(subtype="blocked", verdict=None),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(
        "subtype is blocked but status is closed" in m for m in fail
    )


def test_stale_subtype_fails_when_stamp_matches(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(subtype="stale", verdict=None),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(
        "subtype is stale but the close stamp matches the README pin" in m
        for m in fail
    )


def _repo_closed_agreeing_with_result(
    repo: Path, payload: dict, n_result_commits: int = 1
) -> Path:
    """Git repo: open brief, N result rewrites, then close + RESULT."""
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    md = _write_brief(repo, "7")
    _init_git(repo)
    _commit(repo, "brief open")
    _write_agreeing_pair(repo)
    _commit(repo, "results 1")
    for i in range(2, n_result_commits + 1):
        _touch_results(repo, "7")
        _commit(repo, f"results {i}")
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _write_result(repo / "tasks" / "TASK-7" / "RESULT.json", payload)
    _commit(repo, "close with RESULT")
    return md


def test_probe_out_of_turns_below_cap_is_red(tmp_path, capsys):
    """Must-go-red: fixture RESULT claims out_of_turns; rewrite count is 1."""
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _repo_closed_agreeing_with_result(repo, payload, n_result_commits=1)

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert OUT_OF_TURNS_BELOW_CAP in out
    assert "output_check: FAIL" in out


def test_flipping_success_refuted_to_out_of_turns_without_cap_is_red(
    tmp_path, capsys
):
    """Same tree: success+refuted is green; flipping subtype to out_of_turns is red."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_closed_agreeing_with_result(
        repo, _base_payload(verdict="refuted"), n_result_commits=1
    )
    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "RESULT.json subtype=success verdict='refuted'" in out

    path = repo / "tasks" / "TASK-7" / "RESULT.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["subtype"] = "out_of_turns"
    payload["verdict"] = None
    _write_result(path, payload)
    _commit(repo, "flip subtype to out_of_turns")

    code2, _ = _run_main(repo, "--head-ref", "HEAD")
    out2 = capsys.readouterr().out
    assert code2 == 1, out2
    assert OUT_OF_TURNS_BELOW_CAP in out2


def test_out_of_turns_at_cap_on_escalated_is_green(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    md = _write_brief(repo, "7")
    _init_git(repo)
    _commit(repo, "brief open")
    _write_agreeing_pair(repo)
    _commit(repo, "results 1")
    for i in range(2, 4):
        _touch_results(repo, "7")
        _commit(repo, f"results {i}")
    _set_brief_status(md, "escalated")
    _write_result(
        repo / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(subtype="out_of_turns", verdict=None, turns_used=3),
    )
    _commit(repo, "escalate with RESULT")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "RESULT.json subtype=out_of_turns" in out
    assert "suspended" in out


def test_newly_closed_pr_without_result_is_red(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    md = _write_brief(repo, "7")
    _write_agreeing_pair(repo)
    _init_git(repo)
    base = _commit(repo, "brief open with outputs")
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _commit(repo, "close without RESULT")

    code, _ = _run_main(repo, "--base-ref", base, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert "RESULT.json is missing" in out
    assert "auditor writes RESULT at stop" in out


def test_already_closed_without_result_stays_green_on_main(tmp_path, capsys):
    """TASK-6 shape: closed before this gate, no RESULT, no base-ref."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(f"sha256: `{CORPUS_SHA}`\n", encoding="utf-8")
    md = _agreeing_videos(repo)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _init_git(repo)
    _commit(repo, "already closed, no RESULT")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "RESULT.json" not in out or "missing" not in out
    assert "output_check: PASS" in out
