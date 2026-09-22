"""scope_check classifies by AGENT_RE first and does not grant repair/chore by prefix."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "scope_check", ROOT / "scripts" / "scope_check.py"
)
assert SPEC is not None and SPEC.loader is not None
scope_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope_check)

OWNERS = scope_check.parse_owners("99yyy")


def test_agent_class_does_not_need_an_owner_actor():
    cls = scope_check.classify("cursor/t6-worker-x", actor="agent-bot", owners=OWNERS)
    assert cls.name == "agent"
    assert cls.deny == scope_check.DENY
    assert cls.no_brief is True


def test_box_agent_prefix_is_agent():
    cls = scope_check.classify("box/t6-verifier-x", actor="", owners=frozenset())
    assert cls.name == "agent"


def test_repair_prefix_without_owner_actor_is_rejected():
    with pytest.raises(ValueError) as ei:
        scope_check.classify("repair/t6-x", actor="agent-bot", owners=OWNERS)
    assert str(ei.value) == (
        "scope_check: FAIL branch 'repair/t6-x' class repair is not authorized "
        "for actor 'agent-bot'"
    )


def test_cursor_repair_prefix_without_owner_actor_is_rejected():
    with pytest.raises(ValueError) as ei:
        scope_check.classify("cursor/repair-t6-x", actor="agent-bot", owners=OWNERS)
    assert str(ei.value) == (
        "scope_check: FAIL branch 'cursor/repair-t6-x' class repair is not authorized "
        "for actor 'agent-bot'"
    )


def test_repair_prefix_with_owner_actor_is_repair():
    cls = scope_check.classify("repair/loop-3-1-x", actor="99yyy", owners=OWNERS)
    assert cls.name == "repair"
    assert cls.deny == []
    assert cls.allow is None


def test_chore_prefix_without_owner_actor_is_rejected():
    with pytest.raises(ValueError) as ei:
        scope_check.classify("chore/t6-x", actor="agent-bot", owners=OWNERS)
    assert str(ei.value) == (
        "scope_check: FAIL branch 'chore/t6-x' class chore is not authorized "
        "for actor 'agent-bot'"
    )


def test_chore_class_uses_deny_list():
    cls = scope_check.classify("chore/t6-x", actor="99yyy", owners=OWNERS)
    assert cls.name == "chore"
    assert cls.deny == scope_check.DENY
    assert cls.allow == scope_check.CHORE_ALLOW


def test_agent_is_classified_before_repair_even_on_cursor_r_names():
    # AGENT_RE is cursor|box / [rt] <task> - <scope> -
    # This is an agent branch; it must not fall through to repair.
    cls = scope_check.classify("cursor/r4-audit-x", actor="99yyy", owners=OWNERS)
    assert cls.name == "agent"


def test_chore_owner_may_edit_brief_but_not_github():
    cls = scope_check.classify("chore/t6-x", actor="99yyy", owners=OWNERS)
    assert scope_check.path_blocked("tasks/TASK-6.md", cls) is None
    assert scope_check.path_blocked("README.md", cls) == "DENY"
    assert scope_check.path_blocked(".github/workflows/ci.yml", cls) == "DENY"
    assert scope_check.path_blocked("data/corpus_v2.sqlite", cls) == "DENY"


def test_agent_may_not_edit_brief_or_deny_paths():
    cls = scope_check.classify("cursor/t6-worker-x", actor="99yyy", owners=OWNERS)
    assert scope_check.path_blocked("tasks/TASK-6.md", cls) == "DENY"
    assert scope_check.path_blocked(".github/workflows/ci.yml", cls) == "DENY"
    assert scope_check.path_blocked("tasks/TASK-6/results.json", cls) is None


def test_agent_may_not_edit_scripts_readme_or_loop():
    cls = scope_check.classify("cursor/t6-worker-x", actor="agent-bot", owners=OWNERS)
    assert scope_check.path_blocked("scripts/output_check.py", cls) == "DENY"
    assert scope_check.path_blocked("scripts/history_audit.py", cls) == "DENY"
    assert scope_check.path_blocked("scripts/nested/x.py", cls) == "DENY"
    assert scope_check.path_blocked("README.md", cls) == "DENY"
    assert scope_check.path_blocked("LOOP.md", cls) == "DENY"
    assert scope_check.path_blocked("BACKGROUND.md", cls) is None


def test_chore_may_not_edit_scripts_readme_or_loop():
    cls = scope_check.classify("chore/t6-x", actor="99yyy", owners=OWNERS)
    assert "README.md" not in scope_check.CHORE_ALLOW
    assert "LOOP.md" not in scope_check.CHORE_ALLOW
    assert scope_check.path_blocked("scripts/output_check.py", cls) == "DENY"
    assert scope_check.path_blocked("README.md", cls) == "DENY"
    assert scope_check.path_blocked("LOOP.md", cls) == "DENY"
    assert scope_check.path_blocked("BACKGROUND.md", cls) is None
    assert scope_check.path_blocked("backlog.md", cls) is None


def test_repair_owner_may_edit_scripts_readme_and_loop():
    cls = scope_check.classify("repair/loop-3-2-x", actor="99yyy", owners=OWNERS)
    assert cls.deny == []
    assert scope_check.path_blocked("scripts/output_check.py", cls) is None
    assert scope_check.path_blocked("README.md", cls) is None
    assert scope_check.path_blocked("LOOP.md", cls) is None


def test_investigations_allowed_on_repair_chore_and_agent():
    chore = scope_check.classify("chore/notes-x", actor="99yyy", owners=OWNERS)
    agent = scope_check.classify("cursor/t6-worker-x", actor="agent-bot", owners=OWNERS)
    repair = scope_check.classify("repair/notes-x", actor="99yyy", owners=OWNERS)
    paths = (
        "investigations/README.md",
        "investigations/post-2025-jyutping-drop/README.md",
        "investigations/post-2025-jyutping-drop/scripts/.gitkeep",
    )
    for path in paths:
        assert scope_check.path_blocked(path, chore) is None
        assert scope_check.path_blocked(path, agent) is None
        assert scope_check.path_blocked(path, repair) is None
    assert "LOOP.md" not in scope_check.CHORE_ALLOW
    assert scope_check.path_blocked("LOOP.md", chore) == "DENY"
    assert scope_check.path_blocked("LOOP.md", agent) == "DENY"
    assert scope_check.path_blocked("scripts/scope_check.py", chore) == "DENY"
    assert scope_check.path_blocked("README.md", chore) == "DENY"


# --- authorization is by the pull-request author, actor is the fallback ---


def test_repair_is_authorized_by_the_owner_who_opened_the_pr_even_when_an_agent_pushed():
    # The TASK-9 close (#98): opened by 99yyy, then pushed by cursor[bot].
    # The actor check went red and the same head had to be re-opened as #99.
    cls = scope_check.classify(
        "repair/task-9-close-1f66", actor="cursor[bot]", owners=OWNERS, author="99yyy"
    )
    assert cls.name == "repair"


def test_chore_is_authorized_by_the_owner_who_opened_the_pr_even_when_an_agent_pushed():
    cls = scope_check.classify(
        "chore/task-7-close-f7b2", actor="cursor[bot]", owners=OWNERS, author="99yyy"
    )
    assert cls.name == "chore"


def test_repair_opened_by_a_non_owner_is_rejected_even_when_the_owner_pushed():
    # An owner push must not launder someone else's pull request.
    with pytest.raises(ValueError) as ei:
        scope_check.classify(
            "repair/t6-x", actor="99yyy", owners=OWNERS, author="agent-bot"
        )
    assert str(ei.value) == (
        "scope_check: FAIL branch 'repair/t6-x' class repair is not authorized "
        "for author 'agent-bot'"
    )


def test_without_a_pull_request_the_actor_still_decides():
    # Local ./verify and push runs have no PR author.
    assert scope_check.classify("repair/x-y", actor="99yyy", owners=OWNERS, author="").name == "repair"
    with pytest.raises(ValueError) as ei:
        scope_check.classify("repair/x-y", actor="agent-bot", owners=OWNERS, author="")
    assert str(ei.value) == (
        "scope_check: FAIL branch 'repair/x-y' class repair is not authorized "
        "for actor 'agent-bot'"
    )


def test_author_is_compared_case_insensitively_like_actor():
    cls = scope_check.classify("repair/x-y", actor="cursor[bot]", owners=OWNERS, author="99YYY")
    assert cls.name == "repair"


def test_agent_class_ignores_author():
    cls = scope_check.classify("cursor/t9-worker-x", actor="cursor[bot]", owners=OWNERS, author="99yyy")
    assert cls.name == "agent"
    assert cls.deny == scope_check.DENY
