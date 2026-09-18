#!/usr/bin/env python3
"""Detect a bar being lowered to make a check pass.

A "bar" is anything that decides whether a check passes: a declared expected
value, a tolerance, a threshold, a mutation patch, a counterexample pattern, or
a check in the contract checker itself. A "measured" file is anything a bar
judges: the analysis code, the SQL, the data.

Two rules, both mechanical:

1. One pull request may not change a bar and a measured file together. Lowering
   the bar in the same change that alters what it measures makes the check
   unfalsifiable, and the diff hides it.
2. A pull request that changes a bar at all must state why, as a line beginning
   ``BAR-CHANGE:`` in its body, naming each bar it touches. The line does not
   make the change right; it makes it visible to the round audit, which is where
   judgement belongs.

Counting rule for bars that are code: a NET REMOVAL is a bar change (fewer
checks emitted, fewer counterexample patterns, fewer mutation patches). Adding
checks is never flagged.

Usage:
  python scripts/history_audit.py --base origin/main --pr-body-file body.txt
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

BAR_FILES = ["expected/*", "expected/**"]
# Adding a bar is normal: new code needs its expected value declared in the same
# change (contract clause 9). Only a bar that already existed and then moved, or
# disappeared, is a bar being lowered. Every rule below tests for that.
BAR_COUNTED = {
    "scripts/contract_check.py": (r"\b(?:row|compare_check)\s*\(", "contract checks emitted"),
    "tests/*.py": (r"match\s*=", "counterexample patterns"),
    "tests/**/*.py": (r"match\s*=", "counterexample patterns"),
}
BAR_YAML_KEYS = re.compile(
    r"^\s*(expected_rows|expected_rows_tol|min_judgeable|B|threshold|max_concurrent|"
    r"launch_budget|baseline_model|expected_rows_source)\s*:", re.M
)
BAR_YAML_FILES = ["frame.yaml", "rounds/ROUND-*.yaml"]
MUTATION_GLOB = "tests/mutations/*.patch"

MEASURED = ["src/*", "src/**", "sql/*", "sql/**", "data/*", "data/**",
            "scripts/*.py", "scripts/**/*.py"]


def run(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def changed(base: str) -> list[str]:
    return sorted(p for p in run("git", "diff", "--name-only", f"{base}...HEAD").splitlines() if p.strip())


def match_any(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def count_in(ref: str, path: str, pattern: str) -> int:
    try:
        text = run("git", "show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return 0
    return len(re.findall(pattern, text))


def yaml_bar_keys_touched(base: str, path: str) -> list[str]:
    """Keys whose value moved or vanished. A key that is only added is not a bar change."""
    try:
        diff = run("git", "diff", "--unified=0", f"{base}...HEAD", "--", path)
    except subprocess.CalledProcessError:
        return []
    removed: dict[str, str] = {}
    added: dict[str, str] = {}
    for line in diff.splitlines():
        if line.startswith(("+++", "---")) or not line.startswith(("+", "-")):
            continue
        m = BAR_YAML_KEYS.match(line[1:])
        if not m:
            continue
        key, value = m.group(1), line[1:].split(":", 1)[1].strip()
        (removed if line.startswith("-") else added)[key] = value
    hits = []
    for key, was in removed.items():
        now = added.get(key)
        hits.append(f"{path}:{key} ({was} -> {now if now is not None else 'removed'})")
    return sorted(hits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--pr-body-file", dest="body_FILE")
    args = ap.parse_args()

    files = changed(args.base)
    if not files:
        print("history_audit: no files changed")
        return 0

    bars: list[str] = []
    base_tree = run("git", "ls-tree", "-r", "--name-only", args.base).splitlines()
    for f in files:
        # A file under expected/ counts only if it existed before this change.
        if match_any(f, BAR_FILES) and f in base_tree:
            bars.append(f)
    b_pat = [p for p in base_tree if fnmatch.fnmatch(p, MUTATION_GLOB)]
    h_pat = [p for p in run("git", "ls-tree", "-r", "--name-only", "HEAD").splitlines()
             if fnmatch.fnmatch(p, MUTATION_GLOB)]
    if len(h_pat) < len(b_pat):
        bars.append(f"tests/mutations/ ({len(b_pat)} -> {len(h_pat)} patches)")

    for glob, (pattern, label) in BAR_COUNTED.items():
        for f in files:
            if not fnmatch.fnmatch(f, glob):
                continue
            was, now = count_in(args.base, f, pattern), count_in("HEAD", f, pattern)
            if now < was:
                bars.append(f"{f} ({label} {was} -> {now})")

    for f in files:
        if match_any(f, BAR_YAML_FILES):
            bars.extend(yaml_bar_keys_touched(args.base, f))

    bars = sorted(set(bars))
    measured = sorted(f for f in files if match_any(f, MEASURED))

    print(f"history_audit: {len(files)} file(s) changed")
    print(f"  bars touched:     {bars or 'none'}")
    print(f"  measured touched: {measured or 'none'}")

    failed = False
    if bars and measured:
        print("history_audit: FAIL a bar and the thing it measures changed in one pull request.")
        print("  Split them: change the code in one PR, and the bar in another whose body says why.")
        failed = True

    if bars:
        body = Path(args.body_FILE).read_text(encoding="utf-8") if args.body_FILE and Path(args.body_FILE).is_file() else ""
        declared = [l for l in body.splitlines() if l.strip().startswith("BAR-CHANGE:")]
        if not declared:
            print("history_audit: FAIL a bar changed with no 'BAR-CHANGE: <reason>' line in the pull-request body.")
            failed = True
        else:
            print(f"  declared: {declared[0].strip()[:160]}")

    if failed:
        return 1
    print("history_audit: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
