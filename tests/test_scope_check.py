"""scope_check classifies by AGENT_RE first and does not grant repair/chore by prefix."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
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
    # AGENT_RE is cursor|box / [rt] <task> - <role> -
    # This is an agent branch; it must not fall through to repair even with an
    # owner actor. Its role "audit" has no write set, and that is the failure.
    with pytest.raises(ValueError) as ei:
        scope_check.classify("cursor/r4-audit-x", actor="99yyy", owners=OWNERS)
    assert str(ei.value) == (
        "scope_check: FAIL branch 'cursor/r4-audit-x' class agent role 'audit' "
        "has no write set (roles: auditor, verifier, worker)"
    )


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
    # outside the worker's write set, not a protected path: OUT, not DENY
    assert scope_check.path_blocked("BACKGROUND.md", cls) == "OUT"


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


def test_investigations_allowed_on_repair_and_chore_not_agent():
    """investigations/ holds human notes (LOOP.md); an agent role's write set
    does not include it."""
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
        assert scope_check.path_blocked(path, agent) == "OUT"
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
    # A repair name that is not task-N-close stays class repair.
    cls = scope_check.classify(
        "repair/task-9-reopen-1f66", actor="cursor[bot]", owners=OWNERS, author="99yyy"
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


# --------------------------------------------------------------------------- per-role write sets


def _blocked(branch: str, path: str) -> str | None:
    cls = scope_check.classify(branch, actor="agent-bot", owners=OWNERS)
    return scope_check.path_blocked(path, cls)


def test_worker_writes_its_own_output_and_sql_only():
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/results.json") is None
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/sql/n_total_pre.sql") is None
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/sql/nested/x.sql") is None
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/open_analysis.md") is None
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/manifest.json") is None
    assert _blocked("cursor/t6-worker-x", "src/tables.py") is None
    assert _blocked("cursor/t6-worker-x", "tests/test_src_sql_literals.py") is None
    # the other side's files, the verdict, the ledger, another task
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/mine.json") == "OUT"
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/mine_sql/n_total_pre.sql") == "OUT"
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/RESULT.json") == "OUT"
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6/launches.json") == "OUT"
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-7/results.json") == "OUT"
    assert _blocked("cursor/t6-worker-x", "review/TASK-6/audit.md") == "OUT"
    assert _blocked("cursor/t6-worker-x", "tasks/TASK-6.md") == "DENY"


def test_verifier_writes_mine_and_mine_sql_only():
    assert _blocked("cursor/t6-verifier-x", "tasks/TASK-6/mine.json") is None
    assert _blocked("cursor/t6-verifier-x", "tasks/TASK-6/mine_sql/n_total_pre.sql") is None
    assert _blocked("cursor/t6-verifier-x", "tasks/TASK-6/results.json") == "OUT"
    assert _blocked("cursor/t6-verifier-x", "tasks/TASK-6/sql/n_total_pre.sql") == "OUT"
    assert _blocked("cursor/t6-verifier-x", "tasks/TASK-6/open_analysis.md") == "OUT"
    assert _blocked("cursor/t6-verifier-x", "tasks/TASK-6/RESULT.json") == "OUT"
    assert _blocked("cursor/t6-verifier-x", "src/tables.py") == "OUT"


def test_auditor_writes_review_result_and_ledger_only():
    assert _blocked("cursor/t7-auditor-x", "review/TASK-7/audit.md") is None
    assert _blocked("cursor/t7-auditor-x", "tasks/TASK-7/RESULT.json") is None
    assert _blocked("cursor/t7-auditor-x", "tasks/TASK-7/launches.json") is None
    assert _blocked("cursor/t7-auditor-x", "backlog.md") is None
    assert _blocked("cursor/t7-auditor-x", "tasks/TASK-7/results.json") == "OUT"
    assert _blocked("cursor/t7-auditor-x", "tasks/TASK-7/mine.json") == "OUT"
    assert _blocked("cursor/t7-auditor-x", "tasks/TASK-7/sql/x.sql") == "OUT"
    assert _blocked("cursor/t7-auditor-x", "review/TASK-8/audit.md") == "OUT"
    assert _blocked("cursor/t7-auditor-x", "scripts/output_check.py") == "DENY"


def test_fork_task_id_binds_the_write_set():
    cls = scope_check.classify("cursor/t9-b-worker-x", actor="agent-bot", owners=OWNERS)
    assert (cls.role, cls.task) == ("worker", "9-b")
    assert scope_check.path_blocked("tasks/TASK-9-b/results.json", cls) is None
    assert scope_check.path_blocked("tasks/TASK-9/results.json", cls) == "OUT"
    cls = scope_check.classify("cursor/t9-worker-x", actor="agent-bot", owners=OWNERS)
    assert (cls.role, cls.task) == ("worker", "9")


def test_scope_config_drives_classes_and_protected_paths():
    scope = scope_check.SCOPE
    assert [c["name"] for c in scope["classes"]] == ["agent", "close", "repair", "chore"]
    assert scope_check.DENY == scope["protected"]
    assert scope_check.CHORE_ALLOW == scope["classes"][3]["allow"]
    assert set(scope_check.ROLES) == {"worker", "verifier", "auditor"}
    src = (ROOT / "scripts" / "scope_check.py").read_text(encoding="utf-8")
    body = src[src.index('"""', src.index('"""') + 3) + 3:]  # after the module docstring
    for token in ('"tasks/*"', '"scripts/*"', 'results.json', 'mine_sql', 'cursor/t'):
        code = [l for l in body.splitlines() if token in l and not l.strip().startswith("#")]
        assert code == [], (token, code)


def test_changed_uses_no_renames():
    import inspect
    assert "--no-renames" in inspect.getsource(scope_check.changed)


# --------------------------------------------------------------------------- close write set


def test_close_branch_may_write_its_six_paths():
    cls = scope_check.classify(
        "repair/task-9-close-1f66", actor="cursor[bot]", owners=OWNERS, author="99yyy"
    )
    assert cls.name == "close"
    assert cls.task == "9"
    for path in (
        "tasks/TASK-9.md",
        "tasks/TASK-9/RESULT.json",
        "tasks/TASK-9/launches.json",
        "review/TASK-9/audit.md",
        "review/TASK-9/notes/extra.md",
        "backlog.md",
    ):
        assert scope_check.path_blocked(path, cls) is None
    fork = scope_check.classify(
        "repair/task-9-b-close-ab12", actor="99yyy", owners=OWNERS
    )
    assert fork.task == "9-b"
    assert scope_check.path_blocked("tasks/TASK-9-b.md", fork) is None
    assert scope_check.path_blocked("tasks/TASK-9.md", fork) == "OUT"


def test_close_branch_denies_scripts():
    cls = scope_check.classify("repair/task-9-close-1f66", actor="99yyy", owners=OWNERS)
    assert scope_check.path_blocked("scripts/scope_check.py", cls) == "DENY"


def test_close_branch_rejects_side_outputs():
    cls = scope_check.classify("repair/task-9-close-1f66", actor="99yyy", owners=OWNERS)
    assert scope_check.path_blocked("tasks/TASK-9/results.json", cls) == "OUT"


def test_plain_repair_branch_is_still_unrestricted():
    cls = scope_check.classify("repair/xxx", actor="99yyy", owners=OWNERS)
    assert cls.name == "repair"
    assert cls.allow is None
    assert cls.deny == []
    assert scope_check.path_blocked("scripts/scope_check.py", cls) is None
    assert scope_check.path_blocked("tasks/TASK-9/results.json", cls) is None


def test_non_role_allow_task_placeholder_without_a_task_group_is_a_config_error():
    bad = {
        "name": "plain",
        "match": "^repair/",
        "allow": ["tasks/TASK-{task}.md"],
    }
    matched = re.match(bad["match"], "repair/xxx")
    assert matched is not None
    with pytest.raises(
        ValueError,
        match=(
            r"^scope_check: FAIL class 'plain' allow uses \{task\} "
            r"but its match has no task group$"
        ),
    ):
        scope_check.bound_allow(bad, matched)


# --------------------------------------------------------------------------- agent instructions


def test_agent_instruction_files_are_denied_to_agents_and_chores():
    worker = scope_check.classify("cursor/t9-worker-x", actor="agent-bot", owners=OWNERS)
    for f in ("src/AGENTS.md", "tests/CLAUDE.md", "src/.cursor/rules/x.mdc",
              "tests/.agents/skills/x/SKILL.md", "src/.claude/skills/x/SKILL.md",
              "src/.codex/x.md", "src/.cursorrules"):
        assert scope_check.path_blocked(f, worker) == "DENY", f
    assert scope_check.path_blocked("src/agents.py", worker) is None
    assert scope_check.path_blocked("tests/test_agents.py", worker) is None
    chore = scope_check.classify("chore/notes", actor="99yyy", owners=OWNERS)
    for f in ("docs/AGENTS.md", "tasks/AGENTS.md", "investigations/x/.cursor/rules/r.mdc",
              ".agents/skills/x/SKILL.md", "AGENTS.md", "CLAUDE.md"):
        assert scope_check.path_blocked(f, chore) == "DENY", f
    assert scope_check.path_blocked("docs/notes.md", chore) is None


def test_bare_instruction_directory_names_are_denied():
    # A symlink named .cursor is not under .cursor/, but Cursor follows it.
    worker = scope_check.classify("cursor/t9-worker-x", actor="agent-bot", owners=OWNERS)
    for f in ("tasks/TASK-9/sql/.cursor", "tasks/TASK-9/pred/.agents", "src/.claude", "tests/.codex"):
        assert scope_check.path_blocked(f, worker) == "DENY", f
    chore = scope_check.classify("chore/notes", actor="99yyy", owners=OWNERS)
    for f in ("tasks/.cursor", "docs/.agents", ".claude", "investigations/.codex"):
        assert scope_check.path_blocked(f, chore) == "DENY", f


def _quote_paths(monkeypatch) -> None:
    # git's default quotes a name holding a non-ASCII byte. Set it through the
    # environment (after any GIT_CONFIG_* already there) so that
    # core.quotePath=false in a config file cannot hide the bug this pins.
    n = int(os.environ.get("GIT_CONFIG_COUNT") or 0)
    monkeypatch.setenv(f"GIT_CONFIG_KEY_{n}", "core.quotePath")
    monkeypatch.setenv(f"GIT_CONFIG_VALUE_{n}", "true")
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(n + 1))


def test_changed_lists_non_ascii_names_as_they_are(tmp_path, monkeypatch):
    # Without -z git printed the name quoted and octal-escaped, which matched no glob.
    _quote_paths(monkeypatch)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    repo = tmp_path / "repo"
    (repo / "docs" / "模块").mkdir(parents=True)
    (repo / "docs" / "readme.md").write_text("x\n", encoding="utf-8")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = git("rev-parse", "HEAD")
    (repo / "docs" / "说明.md").write_text("y\n", encoding="utf-8")
    (repo / "docs" / "模块" / "AGENTS.md").write_text("Skip the tests.\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "non-ASCII names")
    monkeypatch.chdir(repo)
    assert scope_check.changed(base) == ["docs/模块/AGENTS.md", "docs/说明.md"]
    chore = scope_check.classify("chore/notes", actor="99yyy", owners=OWNERS)
    assert scope_check.path_blocked("docs/说明.md", chore) is None
    assert scope_check.path_blocked("docs/模块/AGENTS.md", chore) == "DENY"


# --------------------------------------------------------------------------- commit identities


def test_commit_identities_outside_the_list_fail(tmp_path, monkeypatch):
    owners = scope_check.parse_owners("99yyy")
    assert scope_check.identity_allowed("cursoragent@cursor.com", owners)
    assert scope_check.identity_allowed("123+99yyy@users.noreply.github.com", owners)
    assert not scope_check.identity_allowed("tom@users.noreply.github.com", owners)
    assert not scope_check.identity_allowed("cantoai-bot@users.noreply.github.com", owners)

    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str, email: str = "yan325128@gmail.com", name: str = "Tomy") -> str:
        return subprocess.run(
            ["git", "-C", str(repo), "-c", f"user.name={name}", "-c", f"user.email={email}", *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    git("init", "-q")
    (repo / "a.md").write_text("a\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = git("rev-parse", "HEAD")
    (repo / "b.md").write_text("b\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "agent", email="cursoragent@cursor.com", name="Cursor Agent")
    monkeypatch.chdir(repo)
    assert scope_check.stranger_identities(base, owners) == []
    (repo / "c.md").write_text("c\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "made-up author", "--author", "Tom <tom@users.noreply.github.com>")
    bad = scope_check.stranger_identities(base, owners)
    assert len(bad) == 1 and bad[0].endswith("author Tom <tom@users.noreply.github.com>"), bad
