"""Fork briefs keep the parent's numbers/n fences; depth > 2 is blocked.

Probe class: TASK-N-b that changes one numbers tolerance is green on main's
checker (no fork rule) and red here. Opening -d is red. Parent RESULT.json
is immutable after the child brief is added.
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
    _run_main,
    _set_brief_status,
    _set_corpus_sha,
    _write_brief,
    output_check,
)
from tests.test_result_json import (
    _base_payload,
    _repo_closed_agreeing_with_result,
    _write_agreeing_pair,
    _write_result,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True)
    try:
        yield c
    finally:
        c.close()

HYP = "Agreement falls after 2025."
WHY = "n_count is 567."
NUMBERS_FAIL = "```numbers fence is not byte-identical"
N_FAIL = "```n fence is not byte-identical"
THIRD_FORK = "a third fork must be blocked"


def _prior(parent: str = "TASK-7", verdict: str = "refuted") -> str:
    return (
        "## Prior Attempts\n\n"
        f"- parent: {parent}\n"
        f"- hypothesis: {HYP}\n"
        f"- {('verdict: ' + verdict) if verdict != 'out_of_turns' else 'subtype: out_of_turns'}\n"
        f"- why: {WHY}\n"
        f"- n_count: 567\n"
    )


def _child_text(
    parent_md: Path,
    *,
    child: str = "7-b",
    status: str = "open",
    mutate_numbers: bool = False,
    mutate_n: bool = False,
    prior: str | None = None,
    parent_name: str = "TASK-7",
    extra_prose: str = "The gap is rare characters.\n\n",
) -> str:
    parent_text = parent_md.read_text(encoding="utf-8")
    numbers = output_check.fence_interior(parent_text, "numbers") or ""
    n_block = output_check.fence_interior(parent_text, "n")
    if mutate_numbers:
        numbers = numbers.replace("  0\n", "  1\n", 1)
        if numbers == (output_check.fence_interior(parent_text, "numbers") or ""):
            raise AssertionError("tolerance mutation did not change the numbers fence")
    if mutate_n and n_block is not None:
        n_block = n_block.replace("567", "1", 1)
    body = f"# TASK-{child}\n\nstatus: {status}\n\n{extra_prose}"
    body += f"```numbers{numbers}```\n"
    if n_block is not None:
        if mutate_n is False:
            body += f"\n```n{n_block}```\n"
        else:
            body += f"\n```n{n_block}```\n"
    elif mutate_n:
        body += "\n```n\nn_count  1\n```\n"
    body += "\n" + (prior if prior is not None else _prior(parent_name))
    return body


def _write_child(root: Path, parent_md: Path, **kwargs: object) -> Path:
    child = str(kwargs.pop("child", "7-b"))
    text = _child_text(parent_md, child=child, **kwargs)  # type: ignore[arg-type]
    path = root / "tasks" / f"TASK-{child}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _parent_result(root: Path, n: str = "7", **overrides: object) -> None:
    payload = _base_payload(n=n, why=WHY, hypothesis=HYP, **overrides)
    _write_result(root / "tasks" / f"TASK-{n}" / "RESULT.json", payload)


def test_parse_fork_id_root_and_letters():
    root = output_check.parse_fork_id("6")
    assert root is not None
    assert root.depth == 0 and root.parent is None and root.letter is None
    b = output_check.parse_fork_id("6-b")
    assert b is not None and b.depth == 1 and b.parent == "6"
    c = output_check.parse_fork_id("6-c")
    assert c is not None and c.depth == 2 and c.parent == "6-b"
    d = output_check.parse_fork_id("6-d")
    assert d is not None and d.letter == "d" and d.letter not in output_check.FORK_DEPTH
    assert output_check.parse_fork_id("notes") is None


def test_task_ids_from_paths_letter_suffix():
    assert output_check.task_ids_from_paths(["tasks/TASK-7-b.md"]) == frozenset({"7-b"})
    assert output_check.task_ids_from_paths(
        ["tasks/TASK-7-b/RESULT.json"]
    ) == frozenset({"7-b"})
    assert output_check.task_ids_from_paths(["tasks/TASK-7-c.md"]) == frozenset({"7-c"})


def test_fence_interior_is_the_raw_block_body(tmp_path):
    md = _write_brief(tmp_path, "7")
    text = md.read_text(encoding="utf-8")
    got = output_check.fence_interior(text, "numbers")
    assert got is not None
    assert "n_count  0" in got
    assert output_check.fence_interior(text, "n") is None


def test_identical_fork_is_green(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path)
    child = _write_child(tmp_path, md)
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert fail == [], fail


def test_mutated_numbers_tolerance_is_red(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path)
    child = _write_child(tmp_path, md, mutate_numbers=True)
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(NUMBERS_FAIL in m and "new task" in m for m in fail), fail


def test_mutated_n_fence_is_red(conn, tmp_path):
    md = _agreeing_videos(tmp_path, n_block="n_count  567\n", row_n=567)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path)
    child = _write_child(tmp_path, md, mutate_n=True)
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(N_FAIL in m or "```n fence is present" in m for m in fail), fail


def test_missing_prior_attempts_is_red(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path)
    child = _write_child(tmp_path, md, prior="")
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any("no '## Prior Attempts' section" in m for m in fail), fail


def test_opening_letter_d_is_red(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path)
    child = _write_child(tmp_path, md, child="7-d")
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any(THIRD_FORK in m and "TASK-7-d" in m for m in fail), fail


def test_fork_from_supported_is_red(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path, verdict="supported")
    child = _write_child(tmp_path, md)
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any("verdict is refuted" in m for m in fail), fail


def test_fork_from_out_of_turns_is_green(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "escalated")
    _parent_result(tmp_path, subtype="out_of_turns", verdict=None)
    child = _write_child(
        tmp_path, md, prior=_prior(verdict="out_of_turns")
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert fail == [], fail


def test_parent_must_stay_terminal(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _parent_result(tmp_path)
    child = _write_child(tmp_path, md)
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any("status is open" in m and "stays closed or escalated" in m for m in fail), fail


def test_missing_parent_brief_is_red(conn, tmp_path):
    child = _write_brief(tmp_path, "8-b")
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any("parent tasks/TASK-8.md is missing" in m for m in fail), fail


def test_child_result_fields_must_match_suffix(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path)
    child_md = _write_child(tmp_path, md, child="7-b", status="closed")
    _set_corpus_sha(child_md, CORPUS_SHA)
    _write_agreeing_pair(tmp_path, "7-b")
    _write_result(
        tmp_path / "tasks" / "TASK-7-b" / "RESULT.json",
        _base_payload(
            n="7-b",
            forked_from="TASK-9",
            fork_depth=1,
            why=WHY,
            hypothesis="Rare characters explain the gap.",
        ),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child_md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any("forked_from must be 'TASK-7'" in m for m in fail), fail


def test_child_result_correct_fields_are_green(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path)
    child_md = _write_child(tmp_path, md, child="7-b", status="closed")
    _set_corpus_sha(child_md, CORPUS_SHA)
    _write_agreeing_pair(tmp_path, "7-b")
    _write_result(
        tmp_path / "tasks" / "TASK-7-b" / "RESULT.json",
        _base_payload(
            n="7-b",
            forked_from="TASK-7",
            fork_depth=1,
            why=WHY,
            hypothesis="Rare characters explain the gap.",
        ),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, child_md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert fail == [], fail


def test_root_result_cannot_claim_a_parent(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _write_result(
        tmp_path / "tasks" / "TASK-7" / "RESULT.json",
        _base_payload(forked_from="TASK-6", fork_depth=1),
    )
    fail: list[str] = []
    output_check.check_task(
        tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
    )
    assert any("forked_from must be null and fork_depth 0 on a root task" in m for m in fail), fail


def test_live_task_6_has_no_fork_and_still_agrees(conn):
    assert not (ROOT / "tasks" / "TASK-6-b.md").is_file()
    assert not (ROOT / "tasks" / "TASK-6-c.md").is_file()
    md = ROOT / "tasks" / "TASK-6.md"
    fail: list[str] = []
    output_check.check_task(ROOT, md, conn, 60.0, None, None, fail, CORPUS_SHA)
    assert fail == []


def test_probe_mutated_tolerance_is_red_under_this_checker(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = _base_payload(verdict="refuted", why=WHY, hypothesis=HYP)
    md = _repo_closed_agreeing_with_result(repo, payload, n_result_commits=1)
    _write_child(repo, md, mutate_numbers=True)
    _commit(repo, "fork with mutated tolerance")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert NUMBERS_FAIL in out
    assert "new task" in out
    assert "output_check: FAIL" in out


def test_identical_fork_passes_full_checker(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = _base_payload(verdict="refuted", why=WHY, hypothesis=HYP)
    md = _repo_closed_agreeing_with_result(repo, payload, n_result_commits=1)
    _write_child(repo, md)
    _commit(repo, "fork with identical numbers")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "fork of TASK-7 depth 1" in out
    assert "output_check: PASS" in out


def test_parent_result_edit_after_fork_is_red(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = _base_payload(verdict="refuted", why=WHY, hypothesis=HYP)
    md = _repo_closed_agreeing_with_result(repo, payload, n_result_commits=1)
    _write_child(repo, md)
    _commit(repo, "fork")
    result_PATH = repo / "tasks" / "TASK-7" / "RESULT.json"
    data = json.loads(result_PATH.read_text(encoding="utf-8"))
    data["why"] = "n_count is 567 after an edit."
    _write_result(result_PATH, data)
    _commit(repo, "edit parent RESULT")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert "RESULT.json was edited or deleted after the fork" in out


def test_opening_d_is_red_on_full_checker(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = _base_payload(verdict="refuted", why=WHY, hypothesis=HYP)
    md = _repo_closed_agreeing_with_result(repo, payload, n_result_commits=1)
    _write_child(repo, md, child="7-d")
    _commit(repo, "illegal -d")

    code, _ = _run_main(repo, "--head-ref", "HEAD")
    out = capsys.readouterr().out
    assert code == 1, out
    assert THIRD_FORK in out
    assert "TASK-7-d" in out


def test_depth_two_child_of_b(conn, tmp_path):
    md = _agreeing_videos(tmp_path)
    _set_brief_status(md, "closed")
    _set_corpus_sha(md, CORPUS_SHA)
    _parent_result(tmp_path)
    b = _write_child(tmp_path, md, child="7-b", status="closed")
    _set_corpus_sha(b, CORPUS_SHA)
    _write_agreeing_pair(tmp_path, "7-b")
    b_hyp = "Rare characters explain the gap."
    _write_result(
        tmp_path / "tasks" / "TASK-7-b" / "RESULT.json",
        _base_payload(
            n="7-b",
            subtype="out_of_turns",
            verdict=None,
            forked_from="TASK-7",
            fork_depth=1,
            why=WHY,
            hypothesis=b_hyp,
        ),
    )
    prior = (
        "## Prior Attempts\n\n"
        "- parent: TASK-7-b\n"
        f"- hypothesis: {b_hyp}\n"
        "- subtype: out_of_turns\n"
        f"- why: {WHY}\n"
        "- n_count: 567\n"
    )
    c = _write_child(
        tmp_path,
        b,
        child="7-c",
        parent_name="TASK-7-b",
        prior=prior,
    )
    fail: list[str] = []
    output_check.check_task(tmp_path, c, conn, 60.0, None, None, fail, CORPUS_SHA)
    assert fail == [], fail
