#!/usr/bin/env python3
"""Write-scope check for parallel Cloud Agent branches.

A branch named ``cursor/r<N>-<scope_id>-...`` may only change paths matched by
``rounds/ROUND-<N>.yaml: write_scopes.<scope_id>`` (a list of glob patterns).
Branches that do not follow the naming pattern are not checked (exit 0), so
human commits and the coordinator's own commits are unaffected.

Usage (CI):  python scripts/scope_check.py --branch "$HEAD_REF" --base origin/main
Exit 1 with the offending paths printed when the scope is violated, when the
round file or scope id is missing, or when a scoped branch changes nothing.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

import yaml

BRANCH_RE = re.compile(r"^cursor/r(?P<round>\d+)-(?P<scope>[a-z0-9_]+)-")


def changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    return sorted(p for p in out.splitlines() if p.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--rounds-dir", dest="rounds_DIR", required=True)
    args = ap.parse_args()

    m = BRANCH_RE.match(args.branch)
    if not m:
        print(f"scope_check: branch {args.branch!r} is not a scoped agent branch; nothing to check")
        return 0
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
    patterns = list(scopes[scope_id])
    files = changed_files(args.base)
    if not files:
        print("scope_check: FAIL scoped branch changed no files")
        return 1
    outside = [f for f in files if not any(fnmatch.fnmatch(f, p) for p in patterns)]
    print(f"scope_check: branch={args.branch} scope={scope_id} patterns={patterns}")
    for f in files:
        print(("  OUTSIDE " if f in outside else "  ok      ") + f)
    if outside:
        print(f"scope_check: FAIL {len(outside)} file(s) outside write scope {scope_id!r}")
        return 1
    print("scope_check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
