#!/usr/bin/env python3
"""The two independent computations must agree.

Each task declares, in a fenced ``numbers`` block inside ``tasks/TASK-<N>.md``,
the numbers it must produce and the tolerance each one gets:

    ```numbers
    # name                 tol
    gap_all_pp             0.05
    agree_film_pre         0.0005
    ```

The task brief declares names, definitions and tolerances. It never declares
values: a value written in the brief is a value both agents can copy, and two
agents copying the same number is not agreement.

``worker`` writes ``tasks/TASK-<N>/results.json``:

    [{"name": ..., "value": <number>, "n": <int>, "query": "sql/<file>.sql"}]

``verifier`` recomputes every one of them from the corpus by its own route,
without reading the worker's code, and writes ``tasks/TASK-<N>/verify.json``:

    [{"name": ..., "worker": <number>, "mine": <number>,
      "abs_diff": <number>, "match": <bool>}]

This script checks, for every task that has produced anything:

  * the name set of each file equals the declared set exactly -- a missing
    number and an extra number both fail;
  * every ``query`` names a file that exists, so a value can be replayed;
  * ``abs_diff`` really is ``|worker - mine|`` and ``match`` really is
    ``abs_diff <= tol``, so neither field can be asserted rather than computed;
  * ``verify.json``'s ``worker`` column equals ``results.json``'s ``value``,
    so the verifier judged what the worker actually submitted;
  * no row has ``match: false``.

A task whose outputs do not exist yet is reported and skipped. A task with no
``numbers`` block is reported and skipped.

Usage:
    python scripts/output_check.py [--repo-root .]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

BLOCK = re.compile(r"^```numbers\s*$(.*?)^```\s*$", re.M | re.S)
RESULT_KEYS = {"name", "value", "n", "query"}
VERIFY_KEYS = {"name", "worker", "mine", "abs_diff", "match"}
EPS = 1e-9


def declared(md: Path) -> dict[str, float] | None:
    m = BLOCK.search(md.read_text(encoding="utf-8"))
    if not m:
        return None
    out: dict[str, float] = {}
    for line in m.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"{md}: numbers line is not '<name> <tol>': {line!r}")
        out[parts[0]] = float(parts[1])
    if not out:
        return None
    return out


def rows(path: Path, keys: set[str]) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: top level must be a list")
    for i, r in enumerate(data):
        if not isinstance(r, dict) or set(r) != keys:
            raise ValueError(f"{path}[{i}]: keys must be exactly {sorted(keys)}, got {sorted(r) if isinstance(r, dict) else type(r).__name__}")
    return data


def names_equal(label: str, got: list[str], want: set[str], fail: list[str]) -> None:
    g = set(got)
    if len(got) != len(g):
        fail.append(f"{label}: duplicate name(s)")
    for extra in sorted(g - want):
        fail.append(f"{label}: {extra} is not declared in the numbers block")
    for missing in sorted(want - g):
        fail.append(f"{label}: {missing} is declared but absent")


def check_task(root: Path, md: Path, fail: list[str]) -> None:
    n = md.stem.split("-", 1)[1]
    try:
        want = declared(md)
    except ValueError as e:
        fail.append(str(e))
        return
    if want is None:
        print(f"  TASK-{n}: no numbers block; skipped")
        return

    d = root / "tasks" / f"TASK-{n}"
    res_p, ver_p = d / "results.json", d / "verify.json"
    if not res_p.is_file() and not ver_p.is_file():
        print(f"  TASK-{n}: {len(want)} number(s) declared, no output yet; skipped")
        return

    results: dict[str, float] = {}
    if res_p.is_file():
        try:
            rs = rows(res_p, RESULT_KEYS)
        except ValueError as e:
            fail.append(str(e)); return
        names_equal(f"results.json", [r["name"] for r in rs], set(want), fail)
        for r in rs:
            results[r["name"]] = float(r["value"])
            if not isinstance(r["n"], int) or r["n"] < 0:
                fail.append(f"results.json:{r['name']}: n must be a non-negative integer")
            q = str(r["query"]).strip()
            if not q or not (root / q).is_file():
                fail.append(f"results.json:{r['name']}: query {q!r} names no file in the repository")
        print(f"  TASK-{n}: results.json {len(rs)} row(s)")

    if ver_p.is_file():
        try:
            vs = rows(ver_p, VERIFY_KEYS)
        except ValueError as e:
            fail.append(str(e)); return
        names_equal(f"verify.json", [r["name"] for r in vs], set(want), fail)
        bad = 0
        for r in vs:
            nm = r["name"]
            tol = want.get(nm)
            if tol is None:
                continue
            w, mine, ad = float(r["worker"]), float(r["mine"]), float(r["abs_diff"])
            if not math.isclose(ad, abs(w - mine), rel_tol=1e-9, abs_tol=EPS):
                fail.append(f"verify.json:{nm}: abs_diff {ad} is not |worker - mine| = {abs(w - mine)}")
            if bool(r["match"]) != (ad <= tol + EPS):
                fail.append(f"verify.json:{nm}: match {r['match']} does not follow from abs_diff {ad} and tol {tol}")
            if nm in results and not math.isclose(w, results[nm], rel_tol=1e-9, abs_tol=EPS):
                fail.append(f"verify.json:{nm}: worker {w} is not the value {results[nm]} in results.json")
            if not bool(r["match"]):
                bad += 1
                print(f"    MISMATCH {nm}: worker={w} mine={mine} diff={ad} tol={tol}")
        if bad:
            fail.append(f"verify.json: {bad} number(s) did not match")
        else:
            print(f"  TASK-{n}: verify.json {len(vs)} row(s), all matched")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()

    briefs = sorted((root / "tasks").glob("TASK-*.md")) if (root / "tasks").is_dir() else []
    if not briefs:
        print("output_check: no tasks/TASK-*.md; nothing to check")
        return 0

    print(f"output_check: {len(briefs)} task brief(s)")
    fail: list[str] = []
    for md in briefs:
        check_task(root, md, fail)

    if fail:
        print("output_check: FAIL")
        for f in fail:
            print(f"  {f}")
        return 1
    print("output_check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
