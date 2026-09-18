"""Unit tests for the git-commit pytest gate (no nested pytest invocation)."""
from __future__ import annotations

from scripts.git_commit_pytest_hook import is_git_commit


def test_detects_plain_git_commit() -> None:
    assert is_git_commit("git commit -m 'x'") is True


def test_detects_git_commit_with_flags() -> None:
    assert is_git_commit("git -C . --no-pager commit --amend") is True


def test_ignores_non_commit_git() -> None:
    assert is_git_commit("git status") is False
    assert is_git_commit("git add -A") is False
    assert is_git_commit("git commit-tree HEAD^{tree}") is False
    assert is_git_commit("git commit-graph write") is False


def test_detects_commit_in_compound_command() -> None:
    assert is_git_commit("pytest -q && git commit -m x") is True


def test_non_git_is_not_commit() -> None:
    assert is_git_commit("echo git commit") is False
    assert is_git_commit("python scripts/sql_explain.py") is False
