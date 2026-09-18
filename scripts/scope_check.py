#!/usr/bin/env python3
"""Write-scope check for every pull-request branch.

Branch classes, decided by name:

* ``cursor/r<N>-<scope_id>-...`` or ``box/r<N>-<scope_id>-...``: a round agent.
  May change only paths matched by ``rounds/ROUND-<N>.yaml: write_scopes.<scope_id>``.
* ``chore/...``: the coordinator's declaration and documentation PRs. May change
  only the CHORE_ALLOW paths below (round declarations, the research log, the
  backlog, the top-level documents). Never code, tests, fixtures, or expected values.
* ``repair/...`` or ``cursor/repair-...``: a repair Tom asked for. Unrestricted,
  and therefore visible as such in the history; LOOP.md says when it may be used.
* anything else: fails. There is no unscoped branch class.

Usage (CI):  python scripts/scope_check.py --branch "$HEAD_REF" --base origin/main --rounds-dir rounds
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROUND_RE = re.compile(r"^(?:cursor|box)/r(?P<round>\d+)-(?P<scope>[a-z0-9_]+)-")
REPAIR_RE = re.compile(r"^(?:repair/|cursor/repair-)")
CHORE_RE = re.compile(r"^chore/")

CHORE_ALLOW = [
    "rounds/ROUND-*.md",
    "rounds/ROUND-*.yaml",
    "RESEARCH_LOG.md",
    "backlog.md",
    "LOOP.md",
    "LAYOUT.md",
    "REPORT.md",
    "README.md",
    "SCHEMA.md",
    "STOP",
    "ROUND-*/STATUS.json",
]


def changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    return sorted(p for p in out.splitlines() if p.strip())


def report(branch: str, label: str, patterns: list[str], files: list[str]) -> int:
    outside = [f for f in files if not any(fnmatch.fnmatch(f, p) for p in patterns)]
    print(f"scope_check: branch={branch} class={label} patterns={patterns}")
    for f in files:
        print(("  OUTSIDE " if f in outside else "  ok      ") + f)
    if outside:
        print(f"scope_check: FAIL {len(outside)} file(s) outside {label} scope")
        return 1
    print("scope_check: PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--rounds-dir", dest="rounds_DIR", required=True)
    args = ap.parse_args()
    branch = args.branch

    if REPAIR_RE.match(branch):
        print(f"scope_check: branch {branch!r} is a repair branch; unrestricted by design (see LOOP.md)")
        return 0

    files = changed_files(args.base)
    if not files:
        print("scope_check: FAIL branch changed no files")
        return 1

    if CHORE_RE.match(branch):
        return report(branch, "chore", CHORE_ALLOW, files)

    m = ROUND_RE.match(branch)
    if not m:
        print(f"scope_check: FAIL branch {branch!r} matches no branch class "
              "(cursor/r<N>-<scope>-, box/r<N>-<scope>-, chore/, repair/, cursor/repair-)")
        return 1
    n, scope_id = m.group("round"), m.group("scope")
    round_FILE = Path(args.rounds_DIR) / f"ROUND-{n}.yaml"
    if not round_FILE.is_file():
        print(f"scope_check: FAIL missing {round_FILE}")
        return 1
    cfg = yaml.safe_load(round_FILE.read_text(encoding="utf-8")) or {}
    scopes = cfg.get("write_scopes") or {}
    if scope_id not in scopes:
        print(f"scope_check: FAIL scope id {scope_id!r} not declared in {round_FILE}: {sorted(scopes)}")
        return 1
    return report(branch, f"round {n} / {scope_id}", list(scopes[scope_id]), files)


if __name__ == "__main__":
    sys.exit(main())
