#!/usr/bin/env python3
"""Cursor beforeShellExecution hook: allow ``git commit`` only if pytest passes.

Reads JSON on stdin (Cursor hook protocol). On pytest failure: exit 2 and
emit ``user_message``. Non-commit commands are allowed without running tests
so the hook cannot lock out ``git add`` / ``git status`` / ``git push``.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _strip_env_assignments(parts: list[str]) -> list[str]:
    i = 0
    while i < len(parts) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", parts[i]):
        i += 1
    return parts[i:]


def _git_subcommand(parts: list[str]) -> str | None:
    """Return the git subcommand (commit, status, ...) or None if not a git argv."""
    if not parts:
        return None
    if parts[0] in {"sudo", "command", "nohup", "nice"}:
        parts = parts[1:]
    if not parts:
        return None
    prog = Path(parts[0]).name
    if prog != "git":
        return None
    i = 1
    flags_with_arg = {
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--config-env",
        "-c",
    }
    while i < len(parts):
        p = parts[i]
        if p == "--":
            i += 1
            break
        if p.startswith("-"):
            key = p.split("=", 1)[0]
            if key in flags_with_arg and "=" not in p:
                i += 2
                continue
            i += 1
            continue
        return p
    if i < len(parts):
        return parts[i]
    return None


def is_git_commit(command: str) -> bool:
    """True when a git *commit* subcommand is present (not commit-tree/graph)."""
    if not command or not command.strip():
        return False
    chunks = re.split(r"\s*(?:&&|\|\||;|\n|\||&)\s*", command)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            parts = shlex.split(chunk, posix=True)
        except ValueError:
            parts = chunk.split()
        parts = _strip_env_assignments(parts)
        sub = _git_subcommand(parts)
        if sub == "commit":
            return True
    return False


def _read_command() -> str:
    raw = sys.stdin.read()
    if not raw.strip():
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip()
    if isinstance(payload, dict):
        return str(payload.get("command") or "")
    return raw.strip()


def _allow() -> int:
    sys.stdout.write(json.dumps({"permission": "allow"}))
    sys.stdout.write("\n")
    return 0


def _deny(message: str) -> int:
    sys.stdout.write(
        json.dumps({"permission": "deny", "user_message": message}, ensure_ascii=False)
    )
    sys.stdout.write("\n")
    return 2


def gate_commit(root: Path | None = None) -> int:
    root = root or repo_root()
    env = os.environ.copy()
    env["CANTOAI_COMMIT_HOOK_RUNNING"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return _allow()
    tail = "\n".join(
        [
            (proc.stdout or "").strip()[-2000:],
            (proc.stderr or "").strip()[-2000:],
        ]
    ).strip()
    msg = (
        "git commit blocked: pytest failed. Fix tests before committing "
        "(analysis-contract CI gate).\n" + tail
    )
    return _deny(msg)


def main() -> int:
    command = ""
    try:
        command = _read_command()
        if not is_git_commit(command):
            return _allow()
        return gate_commit()
    except Exception as exc:  # noqa: BLE001 — hook must never crash-open a commit
        if is_git_commit(command):
            return _deny(f"git commit blocked: commit hook error: {exc}")
        return _allow()


if __name__ == "__main__":
    raise SystemExit(main())
