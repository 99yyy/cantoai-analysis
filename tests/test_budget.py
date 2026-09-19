"""Launch ledger: RESULT.turns_used equals len(launches.json); family cap 16.

Probe class: a RESULT claiming subtype success with family ledger length 17
must go red. A RESULT claiming out_of_budget while the family is below 16
must go red. Both trees are green on the main checker (turns_used is
type-only; out_of_budget is an allowed subtype with no cap). That
before/after is recorded in the PR body; this file keeps the after
(must-fail) half so the gate cannot regress without a red test.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.test_output_check import (
    CORPUS_PATH,
    CORPUS_SHA,
    ROOT,
    _run_main,
    output_check,
)
from tests.test_result_json import (
    _base_payload,
    _closed_agreeing,
    _repo_closed_agreeing_with_result,
    _write_launches,
    _write_result,
    launch_records,
)

OVER_CAP = ROOT / "tests" / "fixtures" / "budget_probe" / "over_cap"
UNDER_CAP = ROOT / "tests" / "fixtures" / "budget_probe" / "under_cap"
SUCCESS_OVER = (
    "RESULT.json subtype is success but family TASK-7 launches are 17 "
    "(cap is 16)"
)
OUT_OF_BUDGET_UNDER = (
    "RESULT.json subtype is out_of_budget but family TASK-7 launches are 2 "
    "(cap is 16)"
)


@pytest.fixture
def conn():
    c = sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True)
    try:
        yield c
    finally:
        c.close()


def test_over_cap_fixture_is_success_with_17_launches():
    result = json.loads((OVER_CAP / "RESULT.json").read_text(encoding="utf-8"))
    launches = json.loads((OVER_CAP / "launches.json").read_text(encoding="utf-8"))
    assert result["subtype"] == "success"
    assert result["verdict"] == "refuted"
    assert result["turns_used"] == 17
    assert result["turn_cap"] == 3
    assert len(launches) == 17
    assert "cost_usd" not in result
    assert "budget_usd" not in result
    assert "val_iterations" not in result
    for rec in launches:
        assert set(rec) == {"id", "role", "at"}
        assert "cost_usd" not in rec


def test_under_cap_fixture_is_out_of_budget_with_2_launches():
    result = json.loads((UNDER_CAP / "RESULT.json").read_text(encoding="utf-8"))
    launches = json.loads((UNDER_CAP / "launches.json").read_text(encoding="utf-8"))
    assert result["subtype"] == "out_of_budget"
    assert result["verdict"] is None
    assert result["turns_used"] == 2
    assert len(launches) == 2
    assert "cost_usd" not in result
    assert "val_iterations" not in result


def test_parse_launches_accepts_five_roles(tmp_path):
    path = tmp_path / "launches.json"
    recs = launch_records(5)
    path.write_text(json.dumps(recs), encoding="utf-8")
    got = output_check.parse_launches(path, "7")
    assert [r["role"] for r in got] == [
        "coordinator",
        "worker",
        "verifier",
        "auditor",
        "repair",
    ]


def test_parse_launches_rejects_dollar_fields(tmp_path):
    path = tmp_path / "launches.json"
    rec = launch_records(1)[0]
    rec["cost_usd"] = 1.0
    path.write_text(json.dumps([rec]), encoding="utf-8")
    with pytest.raises(output_check.Fail, match=r"unknown keys cost_usd"):
        output_check.parse_launches(path, "7")


def test_parse_launches_rejects_duplicate_id(tmp_path):
    path = tmp_path / "launches.json"
    recs = launch_records(2)
    recs[1]["id"] = recs[0]["id"]
    path.write_text(json.dumps(recs), encoding="utf-8")
    with pytest.raises(output_check.Fail, match=r"duplicate id 'L1'"):
        output_check.parse_launches(path, "7")


def test_parse_launches_rejects_unknown_role(tmp_path):
    path = tmp_path / "launches.json"
    rec = launch_records(1)[0]
    rec["role"] = "intern"
    path.write_text(json.dumps([rec]), encoding="utf-8")
    with pytest.raises(output_check.Fail, match=r"role must be one of"):
        output_check.parse_launches(path, "7")


def test_family_member_ids_root_and_letters():
    assert output_check.family_member_ids("7") == ("7", "7-b", "7-c")
    assert output_check.family_member_ids("7-b") == ("7", "7-b", "7-c")
    assert output_check.family_member_ids("7-c") == ("7", "7-b", "7-c")


def test_matching_ledger_on_success_passes(conn, tmp_path):
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


def test_missing_ledger_with_result_is_red(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(),
        ledger=False,
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any("launches.json is missing" in m for m in fail)


def test_turns_used_mismatch_is_red(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(),
        ledger=False,
    )
    _write_launches(tmp_path / "tasks" / "TASK-7" / "launches.json", 3)
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(
        "turns_used is 2 but launches.json has 3 records" in m for m in fail
    )


def test_success_with_17_launches_is_red(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    payload = json.loads((OVER_CAP / "RESULT.json").read_text(encoding="utf-8"))
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        payload,
        ledger=False,
    )
    (tmp_path / "tasks" / "TASK-7" / "launches.json").write_text(
        (OVER_CAP / "launches.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(SUCCESS_OVER in m for m in fail), fail


def test_out_of_budget_with_2_launches_is_red(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    payload = json.loads((UNDER_CAP / "RESULT.json").read_text(encoding="utf-8"))
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        payload,
        ledger=False,
    )
    (tmp_path / "tasks" / "TASK-7" / "launches.json").write_text(
        (UNDER_CAP / "launches.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(OUT_OF_BUDGET_UNDER in m for m in fail), fail


def test_out_of_budget_at_cap_is_green(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(subtype="out_of_budget", verdict=None, turns_used=16),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert fail == [], fail


def test_success_at_cap_is_green(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(turns_used=16),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert fail == [], fail


def test_blocked_above_cap_is_green(conn, tmp_path):
    md = _closed_agreeing(tmp_path)
    from tests.test_output_check import _set_brief_status

    _set_brief_status(md, "blocked")
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(subtype="blocked", verdict=None, turns_used=17),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert fail == [], fail


def test_family_sum_over_cap_on_child_success_is_red(conn, tmp_path):
    """Parent 2 + child 15 = 17; child success is red; frozen parent is not."""
    from tests.test_fork import _write_child
    from tests.test_output_check import _set_corpus_sha
    from tests.test_result_json import _write_agreeing_pair

    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(verdict="refuted", why="n_count is 567."),
    )
    child_md = _write_child(tmp_path, md, child="7-b", status="closed")
    _set_corpus_sha(child_md, CORPUS_SHA)
    _write_agreeing_pair(tmp_path, "7-b")
    _write_result(
        tmp_path / "tasks" / "TASK-7-b" / "RESULT.json",
        _base_payload(
            n="7-b",
            forked_from="TASK-7",
            fork_depth=1,
            turns_used=15,
            why="n_count is 567.",
            hypothesis="Rare characters explain the gap.",
        ),
    )
    parent_fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, parent_fail, CORPUS_SHA
    )
    assert not any("launches are 17" in m for m in parent_fail), parent_fail

    child_fail: list[str] = []
    output_check.check_task(
        tmp_path, child_md, conn, 60.0, None, None, child_fail, CORPUS_SHA
    )
    assert any(
        "subtype is success but family TASK-7 launches are 17" in m
        for m in child_fail
    ), child_fail


def test_parent_own_ledger_over_cap_is_red_even_with_child(conn, tmp_path):
    """A parent that itself used 17 launches cannot hide behind a later fork."""
    from tests.test_fork import _write_child

    md = _closed_agreeing(tmp_path)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(verdict="refuted", why="n_count is 567.", turns_used=17),
    )
    _write_child(tmp_path, md)
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(SUCCESS_OVER in m for m in fail), fail


def test_probe_over_cap_success_is_red(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = json.loads((OVER_CAP / "RESULT.json").read_text(encoding="utf-8"))
    _repo_closed_agreeing_with_result(repo, payload, n_result_commits=1)

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert SUCCESS_OVER in out
    assert "output_check: FAIL" in out


def test_probe_out_of_budget_under_cap_is_red(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = json.loads((UNDER_CAP / "RESULT.json").read_text(encoding="utf-8"))
    _repo_closed_agreeing_with_result(repo, payload, n_result_commits=1)

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert OUT_OF_BUDGET_UNDER in out
    assert "output_check: FAIL" in out


def test_task_6_has_no_ledger_and_still_agrees(conn):
    """Transitional: TASK-6 closed before the ledger; do not invent one."""
    assert not (ROOT / "tasks" / "TASK-6" / "launches.json").is_file()
    assert not (ROOT / "tasks" / "TASK-6" / "RESULT.json").is_file()
    md = ROOT / "tasks" / "TASK-6.md"
    fail: list[str] = []
    output_check.check_task(ROOT, md, conn, 60.0, None, None, fail, CORPUS_SHA)
    assert fail == []
