#!/usr/bin/env python3
"""Every branch must belong to a known class.

Four classes, and nothing else:

    cursor/t<N>-<scope>-...          a Cloud Agent working on task N
    box/t<N>-<scope>-...             the same, on the shared machine
    chore/...                        declarations and top-level documents
    repair/... | cursor/repair-...   a tool fix asked for by the repository owner

A branch matching none of them fails. That is the point. The silent pass for an
unrecognised branch name is how commit 15ea35a reached main: it changed three
declared expected values after contract-check had already gone red on the same
branch, and nothing looked at it because the branch name matched no pattern.

What each class may touch:

    agent   anything except DENY
    chore   only CHORE_ALLOW, which already excludes everything in DENY but the
            task briefs, which are the owner's to write
    repair  anything, but the prefix makes it visible in the history

Per-scope path lists are not checked here. They belong to a task declaration,
and until one exists again they are a matter for review.

Usage:
    python scripts/scope_check.py --branch "$HEAD_REF" --base origin/main
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys

AGENT_RE = re.compile(r"^(?:cursor|box)/[rt](?P<task>\d+)-(?P<scope>[a-z0-9_]+)-")
REPAIR_RE = re.compile(r"^(?:repair/|cursor/repair-)")
CHORE_RE = re.compile(r"^chore/")

# Only the owner changes the rules, the corpus, the CI that enforces them, or the
# task brief. An agent may not edit the brief that grades it: the numbers it must
# produce, and the tolerance each one gets, are not its to move. An agent that
# needs one of these changed writes BLOCKED instead.
DENY = [".cursor/*", ".cursor/**", ".github/*", ".github/**",
        "data/*", "data/**", "tasks/*", "tasks/**"]

CHORE_ALLOW = [
    "README.md", "SCHEMA.md", "PIPELINE.md", "REPORT.md", "RESEARCH_LOG.md",
    "backlog.md", "LOOP.md", "STOP", "tasks/*", "tasks/**", "docs/*", "docs/**",
]


def run(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def changed(base: str) -> list[str]:
    return sorted(p for p in run("git", "diff", "--name-only", f"{base}...HEAD").splitlines() if p.strip())


def match_any(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", required=True)
    args = ap.parse_args()

    branch = args.branch.strip()
    if REPAIR_RE.match(branch):
        cls, allow, deny = "repair", None, []
    elif CHORE_RE.match(branch):
        cls, allow, deny = "chore", CHORE_ALLOW, []
    elif AGENT_RE.match(branch):
        cls, allow, deny = "agent", None, DENY
    else:
        print(f"scope_check: FAIL branch {branch!r} matches no branch class")
        print("  allowed prefixes: cursor/t<N>-<scope>-, box/t<N>-<scope>-, chore/, repair/")
        return 1

    files = changed(args.base)
    print(f"scope_check: branch={branch} class={cls} files={len(files)}")

    bad: list[str] = []
    for f in files:
        if match_any(f, deny):
            print(f"  DENY    {f}")
            bad.append(f)
        elif allow is not None and not match_any(f, allow):
            print(f"  OUT     {f}")
            bad.append(f)
        else:
            print(f"  ok      {f}")

    if bad:
        print(f"scope_check: FAIL {len(bad)} file(s) this branch class may not touch")
        if allow is not None:
            print(f"  chore/ may touch: {allow}")
        print(f"  no class but repair/ may touch: {DENY}")
        return 1

    print("scope_check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
