#!/usr/bin/env python3
"""Every number is replayed from the corpus, and every number is computed twice
by two agents that could not see each other's work.

A task brief, ``tasks/TASK-<N>.md``, declares in a fenced ``numbers`` block the
numbers the task owes and the tolerance each one gets, and nothing else:

    ```numbers
    # name                 tol
    n_total_pre            0
    gap_all_pp             0.05
    ```

A brief never declares a *value*. A value in the brief is a value both agents
can copy, and two agents copying one number is not agreement. The denominator
``n`` is different (plan §2.5): the brief may nail it in a fenced ``n`` block,
each row a constant or a ``derived:`` expression, and this script forces the
written ``n`` to that declaration. Pairwise equality of the two agents' ``n``
stays; it is not a substitute. Without the fence, ``n`` is still only compared
across the two files.

Two agents answer it. Neither writes a verdict:

    tasks/TASK-<N>/results.json   worker     [{name, value, n, query}]
    tasks/TASK-<N>/mine.json      verifier   [{name, value, n, query}]

Same shape, no comparison field. This script does the comparing, so ``abs_diff``
and ``match`` cannot be asserted by the agent whose work they judge. The earlier
design had the verifier write both, which made the central check of this loop a
self-report.

``query`` is how a number can be replayed, and it is replayed here:

    tasks/TASK-<N>/sql/<f>.sql   one statement, SELECT or WITH, returning
                                 exactly one row and one column, equal to
                                 ``value`` within tol. EXPLAIN QUERY PLAN must
                                 SCAN or SEARCH a real corpus table
                                 (videos, windows, syllables, runs)
    derived:<expr>               arithmetic over other declared names, over the
                                 values this script replayed -- never over the
                                 values the agent wrote down

So a number in a results file is not a claim. It is a claim plus the route to
it, and CI walks the route.

What this enforces, in order:

  corpus       the corpus hashes to the value recorded in README.md.
  brief        exactly one ``status: open|closed|escalated|blocked`` line;
               a parseable ``numbers`` block. ``escalated`` and ``blocked``
               suspend replay, pairwise agreement, declared-n, identity, and
               edit-count for that task (plan §4.4). An optional fenced
               ``n`` block (plan §2.5) and ``frame`` block (plan §6 identity)
               are parsed here; they are not required of every brief.
  shape        top-level list; every row exactly {name, value, n, query}; the
               name set equals the declared set, so a missing number and an
               extra number both fail; no duplicate name; no duplicate route
               within one file (``route()``-resolved Path, not the raw query
               string: ``sql/../sql/x.sql`` and ``sql/x.sql`` are one file).
               When a ``n`` fence is present its name set must equal the
               numbers set; each row is a non-negative integer constant or a
               ``derived:`` expression.
  route        every SQL path exists, resolves under tasks/TASK-<N>/, and is
               not named by both files; after strip_and_split, no worker
               statement sha256 may equal any verifier statement sha256 (copying
               sql/ into mine_sql/ is not a second computation). Two agents may
               share a definition but not an implementation. A shared
               *derivation* is allowed, because each of its inputs was replayed
               on its own.
  replay       every number equals what its own route produces, within tol.
               A SQL route whose plan never SCAN/SEARCHes a corpus table
               fails, so two constant SELECTs cannot certify agreement.
               Each statement is executed twice and the two numbers must
               be identical; random(), randomblob(), and the strftime('now')
               family in the comment-stripped statement fail, so a jitter
               of (abs(random()) % 5) / 100.0 cannot hide inside tol 0.05.
  agreement    the two files agree on every value within tol and on every n
               exactly. Any disagreement fails, and both numbers are printed.
               Pairwise n equality is not enough (plan §2.5): if a ``n`` fence
               is present, each written ``n`` must also equal the declared
               constant or the ``derived:`` expression evaluated over the
               values this script replayed. Both checks run; neither replaces
               the other. A brief with no ``n`` fence does not activate the
               declared-n check.
  identity     if a ``frame`` fence names ``videos_expected`` and the numbers
               block declares ``n_videos_pre``, ``n_videos_post`` and
               ``n_unassigned_period``, their replayed sum must equal
               ``frame.videos_expected`` (tol ``videos_expected_tol``, 0 if
               that name is absent). The right-hand side is the frame field,
               never a literal 567 in this script. No ``videos_expected``, or
               a task that does not declare those three names: the identity
               does not run.
  attempts     at most three commits touch one output file after the
               latest brief revision (the reset commit): the first and two
               retries. A fourth is not a retry, it is a loop. Recount
               starts from that reset, so reopen after a brief edit does
               not inherit the previous ceiling (plan §4.4).
  independence (pull requests only) the commit that introduced one agent's file
               did not have the other agent's file in its tree.
  blocked-commit
               an empty commit whose subject starts with ``BLOCKED:`` is
               recognized and printed. It is the durable marker when the
               agent cannot edit the brief; the tree equals the parent, so
               merge still leaves a git-log trace (plan §4.4).
  closed       a brief may say ``status: closed`` only when both files are
               present, complete and in full agreement.
  scope        (pull requests only) only a task whose brief or files under
               ``tasks/TASK-N/`` appear in the PR diff is fully checked.
               Other tasks print a frozen summary and cannot fail the PR:
               an ``open`` iterating task on main must not redden an
               unrelated one (plan §4.1). Touching either output file
               re-runs the comparison (plan §4.3). On main, every task is
               still fully checked.

On independence, precisely: this proves a branch did not start from a tree that
already held the other answer, which is how this fails in practice -- the second
agent launched after the first merged, with the answer sitting in its working
copy. It does not prove the agent never fetched the other branch mid-run.
Nothing in CI can prove that; the auditor reads the history for it. Launch both
agents from one starting ref and the check passes for both.

Usage:
    python scripts/output_check.py [--repo-root .]
                                   [--base-ref origin/main --head-ref HEAD]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

BLOCK = re.compile(r"^```numbers\s*$(.*?)^```\s*$", re.M | re.S)
N_FENCE = re.compile(r"^```n\s*$(.*?)^```\s*$", re.M | re.S)
FRAME_FENCE = re.compile(r"^```frame\s*$(.*?)^```\s*$", re.M | re.S)
STATUS = re.compile(
    r"^status:[ \t]*(open|closed|escalated|blocked)[ \t]*$", re.M
)
PERIOD_IDENTITY = ("n_videos_pre", "n_videos_post", "n_unassigned_period")
VIDEOS_EXPECTED = "videos_expected"
VIDEOS_EXPECTED_TOL = "videos_expected_tol"
README_SHA = re.compile(r"sha256:\s*`?([0-9a-f]{64})`?")
ROW_KEYS = {"name", "value", "n", "query"}
DERIVED = "derived:"
EPS = 1e-9
MAX_ATTEMPTS = 3
WORKER, VERIFIER = "results.json", "mine.json"
SUSPEND_STATUS = frozenset({"escalated", "blocked"})
BLOCKED_SUBJECT_PREFIX = "BLOCKED:"
# tasks/TASK-N.md or anything under tasks/TASK-N/ (plan §4.1 / §4.3).
TASK_PATH_RE = re.compile(r"^tasks/TASK-([^/]+)(?:\.md|/)")

ALLOWED_BINOP = (ast.Add, ast.Sub, ast.Mult, ast.Div)
ALLOWED_UNARY = (ast.UAdd, ast.USub)

# Real corpus tables. SCAN CONSTANT ROW / sqlite_master / a CTE of the same
# name is not a touch. SQLite prints aliases (SCAN v), so aliases from FROM/JOIN
# are resolved before the name is checked.
CORPUS_TABLES = frozenset({"videos", "windows", "syllables", "runs"})
_IDENT = re.compile(r'("([^"]+)"|`([^`]+)`|\[([^\]]+)\]|(\w+))')
_FROM_JOIN = re.compile(r"(?is)\b(?:from|join)\b")
_AS_KW = re.compile(r"(?is)as\b")
_PLAN_SCAN = re.compile(
    r"(?i)\b(?:SCAN|SEARCH)\s+(?:TABLE\s+)?(?:(?:main|temp)\.)?"
    r"(?P<name>\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|\w+)"
)
_PLAN_CTE = re.compile(r"(?i)\b(?:CO-ROUTINE|MATERIALIZE)\s+(\w+)")
# Non-deterministic SQLite in comment-stripped statement text (plan §2.4).
_RANDOM_CALL = re.compile(r"(?i)\brandom\s*\(")
_RANDOMBLOB_CALL = re.compile(r"(?i)\brandomblob\s*\(")
_CURRENT_NOW = re.compile(r"(?i)\bcurrent_(?:timestamp|date|time)\b")
_NOW_FAMILY_CALL = re.compile(
    r"(?i)\b(?:strftime|date|time|datetime|julianday|unixepoch|timediff)\s*\("
)
_NOT_ALIAS = frozenset(
    {
        "on",
        "where",
        "group",
        "order",
        "limit",
        "join",
        "left",
        "right",
        "inner",
        "cross",
        "full",
        "natural",
        "outer",
        "using",
        "union",
        "except",
        "intersect",
        "select",
        "with",
        "and",
        "or",
        "set",
        "having",
        "window",
        "values",
        "then",
        "else",
        "when",
        "end",
        "from",
        "into",
        "distinct",
        "all",
        "by",
        "asc",
        "desc",
        "offset",
        "fetch",
        "only",
        "rows",
        "row",
        "between",
        "like",
        "glob",
        "is",
        "not",
        "in",
        "exists",
        "case",
        "cast",
        "collate",
        "as",
        "recursive",
        "materialized",
        "returning",
        "nulls",
        "filter",
        "over",
        "partition",
    }
)


class Fail(Exception):
    """A condition this script exists to catch."""


class Brief(NamedTuple):
    """Parsed task brief. ``n_decl`` is None when the brief has no ``n`` fence."""

    status: str
    tol: dict[str, float]
    n_decl: dict[str, str] | None
    frame: dict[str, float]


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol + EPS


def num(v: float) -> str:
    """A count prints as a count; a rate keeps its digits."""
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


# --------------------------------------------------------------------------- git


def git(root: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    if p.returncode != 0:
        raise Fail(f"git {' '.join(args)}: {p.stderr.strip() or 'failed'}")
    return p.stdout


def in_tree(root: Path, rev: str, path: str) -> bool:
    p = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{rev}:{path}"],
        capture_output=True,
        text=True,
    )
    return p.returncode == 0


def commits_touching(root: Path, rev: str, path: str) -> list[str]:
    out = git(root, "log", rev, "--format=%H", "--", path)
    return [l.strip() for l in out.splitlines() if l.strip()]


def reset_commit(root: Path, rev: str, n: str) -> str | None:
    """Latest commit that revised the task brief.

    Recount of output-file rewrites starts from this commit (plan §4.4):
    ``git log <reset>..<rev>`` does not include the reset itself.
    """
    got = commits_touching(root, rev, f"tasks/TASK-{n}.md")
    return got[0] if got else None


def commits_touching_since(
    root: Path, rev: str, path: str, since: str | None
) -> list[str]:
    """Commits that touch ``path`` after ``since`` (exclusive), or all of ``rev``."""
    rng = f"{since}..{rev}" if since else rev
    return commits_touching(root, rng, path)


def is_empty_commit(root: Path, sha: str) -> bool:
    """True when ``sha``'s tree equals its first parent's tree (no file changes)."""
    try:
        tree = git(root, "rev-parse", f"{sha}^{{tree}}").strip()
        parent_tree = git(root, "rev-parse", f"{sha}^^{{tree}}").strip()
    except Fail:
        return False
    return tree == parent_tree


def blocked_empty_commits(
    root: Path, rev: str, since: str | None = None
) -> list[tuple[str, str]]:
    """Empty commits whose subject starts with ``BLOCKED:`` (plan §4.4)."""
    rng = f"{since}..{rev}" if since else rev
    try:
        out = git(root, "log", rng, "--format=%H %s")
    except Fail:
        return []
    found: list[tuple[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, _, subj = line.partition(" ")
        if not subj.startswith(BLOCKED_SUBJECT_PREFIX):
            continue
        if is_empty_commit(root, sha):
            found.append((sha, subj))
    return found


def first_added(root: Path, rng: str, path: str) -> str | None:
    """The earliest commit in ``rng`` that added ``path``, if any."""
    out = git(root, "log", rng, "--diff-filter=A", "--format=%H", "--", path)
    shas = [l.strip() for l in out.splitlines() if l.strip()]
    return shas[-1] if shas else None


def task_ids_from_paths(paths: Iterable[str]) -> frozenset[str]:
    """Task ids whose brief or ``tasks/TASK-N/`` tree appears in ``paths``.

    Touching either output file counts (plan §4.3): a PR that edits
    ``results.json`` or ``mine.json`` must re-run the comparison.
    ``review/TASK-N/`` is not a touch.
    """
    out: set[str] = set()
    for raw in paths:
        m = TASK_PATH_RE.match(raw.replace("\\", "/"))
        if m:
            out.add(m.group(1))
    return frozenset(out)


def pr_diff_names(root: Path, base: str, head: str) -> list[str]:
    """Repo-relative paths in ``base...head`` (the pull-request triple-dot)."""
    out = git(root, "diff", "--name-only", f"{base}...{head}")
    return [l.strip() for l in out.splitlines() if l.strip()]


def frozen_summary(root: Path, md: Path) -> None:
    """Print state for a task this PR did not touch; never fail (plan §4.1)."""
    n = md.stem.split("-", 1)[1]
    try:
        brief = parse_brief(md)
    except Fail:
        print(f"  TASK-{n}: frozen (not touched by this PR); brief not re-checked")
        return
    task_dir = root / "tasks" / f"TASK-{n}"
    present = [k for k in (WORKER, VERIFIER) if (task_dir / k).is_file()]
    files = ", ".join(present) if present else "no output yet"
    extra = "; suspended" if brief.status in SUSPEND_STATUS else ""
    print(
        f"  TASK-{n} [{brief.status}]: frozen (not touched by this PR); "
        f"{len(brief.tol)} number(s) declared; {files}{extra}"
    )


# ------------------------------------------------------------------------- brief


def parse_brief(md: Path) -> Brief:
    text = md.read_text(encoding="utf-8")

    st = STATUS.findall(text)
    if len(st) != 1:
        raise Fail(
            f"{md.name}: needs exactly one line 'status: open', "
            f"'status: closed', 'status: escalated' or 'status: blocked'; "
            f"found {len(st)}"
        )

    m = BLOCK.search(text)
    if not m:
        raise Fail(f"{md.name}: has no fenced ```numbers block")

    tol: dict[str, float] = {}
    for line in m.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise Fail(f"{md.name}: numbers line is not '<name> <tol>': {line!r}")
        name, raw = parts
        if name in tol:
            raise Fail(f"{md.name}: {name} is declared twice")
        try:
            t = float(raw)
        except ValueError:
            raise Fail(f"{md.name}: {name} has a non-numeric tolerance {raw!r}")
        if t < 0:
            raise Fail(f"{md.name}: {name} has a negative tolerance {t}")
        tol[name] = t
    if not tol:
        raise Fail(f"{md.name}: the numbers block is empty")

    n_decl = parse_n_block(md.name, text)
    if n_decl is not None:
        extra = sorted(set(n_decl) - set(tol))
        missing = sorted(set(tol) - set(n_decl))
        if extra or missing:
            bits: list[str] = []
            if extra:
                bits.append("not in the numbers block: " + ", ".join(extra))
            if missing:
                bits.append(
                    "declared in numbers but missing from n: " + ", ".join(missing)
                )
            raise Fail(f"{md.name}: ```n block " + "; ".join(bits))

    return Brief(st[0], tol, n_decl, parse_frame_block(md.name, text))


def parse_n_block(label: str, text: str) -> dict[str, str] | None:
    """Name -> integer spec or ``derived:<expr>``. None when there is no ``n`` fence.

    The fence is optional. When it is present it must not be empty: each line
    is a constant non-negative integer or a ``derived:`` expression (plan §2.5).
    """
    m = N_FENCE.search(text)
    if not m:
        return None
    out: dict[str, str] = {}
    for raw in m.group(1).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise Fail(f"{label}: n line is not '<name> <int|derived:...>': {line!r}")
        name, spec = parts
        if name in out:
            raise Fail(f"{label}: {name} is declared twice in the n block")
        if spec.startswith(DERIVED):
            expr = spec[len(DERIVED) :].strip()
            if not expr:
                raise Fail(f"{label}: {name}: derived: is followed by nothing")
            out[name] = DERIVED + expr
            continue
        bits = spec.split()
        if len(bits) != 1:
            raise Fail(f"{label}: n line is not '<name> <int|derived:...>': {line!r}")
        try:
            v = float(bits[0])
        except ValueError:
            raise Fail(
                f"{label}: {name} n is not a non-negative integer or derived: "
                f"({bits[0]!r})"
            )
        if v < 0 or abs(v - round(v)) > EPS:
            raise Fail(f"{label}: {name} n must be a non-negative integer, got {v}")
        out[name] = str(int(round(v)))
    if not out:
        raise Fail(f"{label}: the n block is empty")
    return out


def parse_frame_block(label: str, text: str) -> dict[str, float]:
    """Numeric ``frame`` entries. Predicate lines are skipped. Empty if no fence.

    The identity in ``check_period_identity`` reads ``videos_expected`` from
    this dict. It does not run when that name is absent, including when the
    brief has no ``frame`` fence at all (plan §6).
    """
    m = FRAME_FENCE.search(text)
    if not m:
        return {}
    out: dict[str, float] = {}
    for raw in m.group(1).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        nums: list[float] = []
        ok = True
        for p in parts[1:]:
            try:
                nums.append(float(p))
            except ValueError:
                ok = False
                break
        if not ok or len(nums) != 1:
            continue
        name = parts[0]
        if name in out:
            raise Fail(f"{label}: {name} is declared twice in the frame block")
        out[name] = nums[0]
    return out


def as_count(label: str, v: float) -> int:
    """A declared ``n`` must be a non-negative integer after evaluation."""
    if v < 0 or abs(v - round(v)) > EPS:
        raise Fail(
            f"{label}: declared n evaluates to {num(v)}, "
            f"which is not a non-negative integer"
        )
    return int(round(v))


def resolve_declared_n(
    label: str, name: str, spec: str, known: dict[str, float]
) -> int:
    """Evaluate one ``n`` fence row over replayed values (never written ones)."""
    tag = f"{label}:{name}.n"
    if spec.startswith(DERIVED):
        expr = spec[len(DERIVED) :].strip()
        try:
            v = eval_derived(tag, expr, known)
        except KeyError as e:
            raise Fail(
                f"{tag}: derived expression {expr!r} cannot be resolved -- "
                f"it names a number that is undeclared, that failed to replay, "
                f"or that depends on this one ({e.args[0]})"
            ) from e
        return as_count(tag, v)
    return as_count(tag, float(spec))


def check_declared_n(
    label: str,
    rows: dict[str, dict],
    n_decl: dict[str, str],
    replayed: dict[str, float],
    fail: list[str],
) -> int:
    """Force each written ``n`` to the brief's declared value (plan §2.5).

    Returns how many names matched. Pairwise worker/verifier equality is a
    separate check and still runs.
    """
    matched = 0
    for name in sorted(n_decl):
        if name not in rows:
            continue
        claimed = rows[name]["n"]
        try:
            want = resolve_declared_n(label, name, n_decl[name], replayed)
        except Fail as e:
            fail.append(str(e))
            continue
        if claimed != want:
            fail.append(
                f"{label}:{name}: n={claimed}, but the brief declares n={want}"
            )
        else:
            matched += 1
    return matched


def check_period_identity(
    task_n: str,
    label: str,
    declared: dict[str, float],
    replayed: dict[str, float],
    frame: dict[str, float],
    fail: list[str],
) -> str | None:
    """``n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected``.

    Activates only when ``videos_expected`` is in ``frame`` and all three names
    are in the numbers block. The right-hand side is the frame field, not a
    numeric literal. Returns a success note, or None if skipped or failed.
    """
    if VIDEOS_EXPECTED not in frame:
        return None
    if not all(nm in declared for nm in PERIOD_IDENTITY):
        return None
    missing = [nm for nm in PERIOD_IDENTITY if nm not in replayed]
    if missing:
        fail.append(
            f"TASK-{task_n}: {label}: period identity needs replayed "
            f"{', '.join(PERIOD_IDENTITY)}; missing {', '.join(missing)}"
        )
        return None
    a, b, c = (replayed[nm] for nm in PERIOD_IDENTITY)
    got = a + b + c
    want = frame[VIDEOS_EXPECTED]
    t = frame.get(VIDEOS_EXPECTED_TOL, 0.0)
    if not close(got, want, t):
        fail.append(
            f"TASK-{task_n}: {label}: "
            f"{PERIOD_IDENTITY[0]} + {PERIOD_IDENTITY[1]} + {PERIOD_IDENTITY[2]} "
            f"= {num(a)} + {num(b)} + {num(c)} = {num(got)}, "
            f"but frame.{VIDEOS_EXPECTED} is {num(want)} (tol {t:g})"
        )
        return None
    return (
        f"{num(a)} + {num(b)} + {num(c)} = {num(got)} = frame.{VIDEOS_EXPECTED}"
    )


def parse_rows(
    path: Path, tol: dict[str, float], fail: list[str], n: str, root: Path
) -> dict[str, dict] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail.append(f"{path.name}: not valid JSON: {e}")
        return None
    if not isinstance(data, list):
        fail.append(f"{path.name}: top level must be a list of rows")
        return None

    ok = True
    rows: dict[str, dict] = {}
    for i, r in enumerate(data):
        if not isinstance(r, dict) or set(r) != ROW_KEYS:
            got = sorted(r) if isinstance(r, dict) else type(r).__name__
            fail.append(f"{path.name}[{i}]: keys must be exactly {sorted(ROW_KEYS)}, got {got}")
            ok = False
            continue
        name = r["name"]
        if name in rows:
            fail.append(f"{path.name}: {name} appears twice")
            ok = False
            continue
        if not isinstance(r["value"], (int, float)) or isinstance(r["value"], bool):
            fail.append(f"{path.name}:{name}: value must be a number")
            ok = False
            continue
        if not isinstance(r["n"], int) or isinstance(r["n"], bool) or r["n"] < 0:
            fail.append(f"{path.name}:{name}: n must be a non-negative integer")
            ok = False
            continue
        rows[name] = r

    extra = sorted(set(rows) - set(tol))
    missing = sorted(set(tol) - set(rows))
    for e in extra:
        fail.append(f"{path.name}: {e} is not declared in the numbers block")
    for m in missing:
        fail.append(f"{path.name}: {m} is declared but absent")
    if extra or missing:
        ok = False

    # Keyed by route() target (resolved Path for SQL, stripped expr for
    # derived), not the raw query string. Otherwise sql/../sql/x.sql and
    # sql/x.sql look like two routes and back two numbers.
    seen: dict[object, str] = {}
    for name, r in rows.items():
        q = str(r["query"]).strip()
        if not q:
            fail.append(f"{path.name}:{name}: query is empty")
            ok = False
            continue
        try:
            _kind, target = route(path.name, n, name, q, root)
        except Fail:
            target = q
        if target in seen:
            fail.append(
                f"{path.name}:{name}: query {q!r} already backs {seen[target]}; "
                f"one route may produce only one number"
            )
            ok = False
        seen[target] = name

    return rows if ok else None


# ------------------------------------------------------------------------- replay


def strip_and_split(text: str) -> list[str]:
    """Comment-stripped statements, splitting on ';' outside string literals."""
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            j = i + 1
            while j < n:
                if text[j] == c:
                    if c == "'" and j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            buf.append(text[i:j])
            i = j
            continue
        if text.startswith("--", i):
            j = text.find("\n", i)
            if j < 0:
                break
            buf.append("\n")
            i = j + 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                break
            buf.append(" ")
            i = j + 2
            continue
        if c == ";":
            out.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def statement_sha256(text: str) -> str:
    """sha256 of the comment-stripped statement text from ``strip_and_split``.

    One statement hashes as itself; several join on ``;``. Leading and trailing
    whitespace are already gone; comments are already gone. Internal whitespace
    is kept, so this is identity after the splitter, not a second canonicalizer.
    """
    stmts = strip_and_split(text)
    body = stmts[0] if len(stmts) == 1 else ";".join(stmts)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def cross_side_sql_hash_collisions(
    n: str,
    root: Path,
    worker: dict[Path, str],
    verifier: dict[Path, str],
) -> list[str]:
    """Any worker SQL hash equal to any verifier SQL hash is a shared implementation."""

    def by_hash(files: dict[Path, str]) -> dict[str, list[tuple[Path, str]]]:
        out: dict[str, list[tuple[Path, str]]] = {}
        for p, nm in files.items():
            h = statement_sha256(p.read_text(encoding="utf-8"))
            out.setdefault(h, []).append((p, nm))
        return out

    w_h, v_h = by_hash(worker), by_hash(verifier)
    msgs: list[str] = []
    for h in sorted(set(w_h) & set(v_h)):
        for wp, wn in sorted(w_h[h], key=lambda t: t[0].as_posix()):
            for vp, vn in sorted(v_h[h], key=lambda t: t[0].as_posix()):
                if wp == vp:
                    continue
                w_rel = wp.relative_to(root)
                v_rel = vp.relative_to(root)
                msgs.append(
                    f"TASK-{n}: {w_rel} backs {wn} in {WORKER} and "
                    f"{v_rel} backs {vn} in {VERIFIER}; "
                    f"statement sha256 {h} after strip_and_split; "
                    f"the second computation must be its own"
                )
    return msgs


def _mask_strings(text: str) -> str:
    """Replace string literals with spaces so FROM/JOIN inside quotes is ignored."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            j = i + 1
            while j < n:
                if text[j] == c:
                    if c == "'" and j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(" " * (j - i))
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _parse_ident(text: str, i: int) -> tuple[str | None, int]:
    m = _IDENT.match(text, i)
    if not m:
        return None, i
    name = next(g for g in m.groups()[1:] if g is not None)
    return name, m.end()


def from_join_alias_map(stmt: str) -> dict[str, str]:
    """Map FROM/JOIN table names and their aliases to the unquoted table name."""
    text = _mask_strings(stmt)
    out: dict[str, str] = {}
    for m in _FROM_JOIN.finditer(text):
        i = m.end()
        while True:
            i = _skip_ws(text, i)
            if i >= len(text) or text[i] == "(":
                break
            name, i = _parse_ident(text, i)
            if name is None:
                break
            i2 = _skip_ws(text, i)
            if i2 < len(text) and text[i2] == ".":
                name2, i = _parse_ident(text, i2 + 1)
                if name2 is not None:
                    name = name2
                else:
                    i = i2
            table = name.lower()
            i = _skip_ws(text, i)
            as_m = _AS_KW.match(text, i)
            alias = None
            if as_m:
                i = _skip_ws(text, as_m.end())
                alias, i = _parse_ident(text, i)
            else:
                cand, j = _parse_ident(text, i)
                if cand is not None and cand.lower() not in _NOT_ALIAS:
                    alias = cand
                    i = j
            out[table] = table
            if alias:
                out[alias.lower()] = table
            i = _skip_ws(text, i)
            if i < len(text) and text[i] == ",":
                i += 1
                continue
            break
    return out


def plan_touches_corpus(details: list[str], stmt: str) -> bool:
    """True when EXPLAIN QUERY PLAN SCAN/SEARCHes videos, windows, syllables, or runs."""
    ctes = {m.group(1).lower() for d in details for m in _PLAN_CTE.finditer(d)}
    aliases = from_join_alias_map(stmt)
    for detail in details:
        m = _PLAN_SCAN.search(detail)
        if not m:
            continue
        raw = m.group("name")
        name = raw[1:-1] if len(raw) >= 2 and raw[0] in '"[`' else raw
        name = name.lower()
        if name in {"constant", "subquery"} or name in ctes:
            continue
        if aliases.get(name, name) in CORPUS_TABLES:
            return True
    return False


def _sql_string_literals(text: str) -> list[str]:
    """Unescaped contents of single-quoted SQL string literals."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "'":
            i += 1
            continue
        j = i + 1
        buf: list[str] = []
        while j < n:
            if text[j] == "'":
                if j + 1 < n and text[j + 1] == "'":
                    buf.append("'")
                    j += 2
                    continue
                out.append("".join(buf))
                j += 1
                break
            buf.append(text[j])
            j += 1
        i = j
    return out


def _paren_group(text: str, open_i: int) -> str | None:
    """Return the ``(...)`` group starting at ``open_i``, skipping quoted spans."""
    depth = 0
    i, n = open_i, len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            quote = c
            i += 1
            while i < n:
                if text[i] == quote:
                    if quote == "'" and i + 1 < n and text[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_i : i + 1]
        i += 1
    return None


def forbidden_nondeterminism(stmt: str) -> str | None:
    """Banned token in comment-stripped statement text, or None.

    ``random()``, ``randomblob()``, and the ``strftime('now')`` family:
    date/time functions whose timestring is the literal ``'now'``, plus
    CURRENT_DATE / CURRENT_TIME / CURRENT_TIMESTAMP.
    """
    hits: list[tuple[int, str]] = []
    for m in _RANDOMBLOB_CALL.finditer(stmt):
        hits.append((m.start(), "randomblob()"))
    for m in _RANDOM_CALL.finditer(stmt):
        hits.append((m.start(), "random()"))
    for m in _CURRENT_NOW.finditer(stmt):
        hits.append((m.start(), "strftime('now')"))
    for m in _NOW_FAMILY_CALL.finditer(stmt):
        args = _paren_group(stmt, m.end() - 1)
        if args is None:
            continue
        if any(s.lower() == "now" for s in _sql_string_literals(args)):
            hits.append((m.start(), "strftime('now')"))
    if not hits:
        return None
    hits.sort(key=lambda t: t[0])
    return hits[0][1]


def run_sql(conn: sqlite3.Connection, label: str, sql_path: Path, seconds: float) -> float:
    stmts = strip_and_split(sql_path.read_text(encoding="utf-8"))
    if len(stmts) != 1:
        raise Fail(f"{label}: {sql_path.name} holds {len(stmts)} statements; it must hold exactly one")
    stmt = stmts[0]
    if not re.match(r"(?is)^\s*(select|with)\b", stmt):
        raise Fail(f"{label}: {sql_path.name} must begin with SELECT or WITH")

    banned = forbidden_nondeterminism(stmt)
    if banned is not None:
        raise Fail(
            f"{label}: {sql_path.name} uses {banned}; "
            f"a replayed number must be deterministic"
        )

    try:
        plan_rows = conn.execute("EXPLAIN QUERY PLAN " + stmt).fetchall()
    except sqlite3.Error as e:
        raise Fail(f"{label}: {sql_path.name} would not run: {e}")
    details = [str(r[-1]) for r in plan_rows]
    if not plan_touches_corpus(details, stmt):
        plan_txt = "; ".join(details) if details else "(empty)"
        raise Fail(
            f"{label}: {sql_path.name} EXPLAIN QUERY PLAN does not SCAN or SEARCH "
            f"a corpus table (videos, windows, syllables, runs); plan: {plan_txt}"
        )

    deadline = time.monotonic() + seconds

    def execute_once() -> float:
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0, 100_000
        )
        try:
            cur = conn.execute(stmt)
            got = cur.fetchmany(2)
        except sqlite3.OperationalError as e:
            if "interrupt" in str(e).lower():
                raise Fail(f"{label}: {sql_path.name} ran longer than {seconds:g}s")
            raise Fail(f"{label}: {sql_path.name} would not run: {e}")
        except sqlite3.Error as e:
            raise Fail(f"{label}: {sql_path.name} would not run: {e}")
        finally:
            conn.set_progress_handler(None, 0)

        if len(got) != 1:
            raise Fail(
                f"{label}: {sql_path.name} returned "
                f"{'no rows' if not got else 'more than one row'}; it must return exactly one"
            )
        if len(got[0]) != 1:
            raise Fail(
                f"{label}: {sql_path.name} returned {len(got[0])} columns; "
                f"it must return exactly one"
            )
        v = got[0][0]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise Fail(f"{label}: {sql_path.name} returned {v!r}, which is not a number")
        return float(v)

    first = execute_once()
    second = execute_once()
    if first != second:
        raise Fail(
            f"{label}: {sql_path.name} returned {num(first)} then {num(second)}; "
            f"a replayed number must be deterministic"
        )
    return first


def eval_derived(label: str, expr: str, known: dict[str, float]) -> float:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise Fail(f"{label}: derived expression does not parse: {e.msg}")

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in known:
                raise KeyError(node.id)
            return known[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ALLOWED_UNARY):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and isinstance(node.op, ALLOWED_BINOP):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if b == 0:
                raise Fail(f"{label}: derived expression divides by zero")
            return a / b
        raise Fail(
            f"{label}: a derived expression may use only declared names, "
            f"numbers, + - * / and parentheses"
        )

    return ev(tree.body)


def route(label: str, n: str, name: str, q: str, root: Path) -> tuple[str, object]:
    """Resolve a ``query`` into ('derived', expr) or ('sql', path).

    A SQL route has exactly one spelling -- repo-relative, under this task's
    directory. Two spellings of one file would let the two agents share an
    implementation while the strings looked different.
    """
    if q.startswith(DERIVED):
        expr = q[len(DERIVED):].strip()
        if not expr:
            raise Fail(f"{label}:{name}: derived: is followed by nothing")
        return "derived", expr
    prefix = f"tasks/TASK-{n}/"
    if not q.startswith(prefix) or not q.endswith(".sql"):
        raise Fail(
            f"{label}:{name}: query {q!r} must be either {prefix}<...>.sql "
            f"or derived:<expr>"
        )
    p = (root / q).resolve()
    try:
        p.relative_to((root / "tasks" / f"TASK-{n}").resolve())
    except ValueError:
        raise Fail(f"{label}:{name}: query {q!r} does not resolve inside {prefix}")
    if not p.is_file():
        raise Fail(f"{label}:{name}: query {q!r} names no file in the repository")
    return "sql", p


def replay(
    label: str,
    rows: dict[str, dict],
    tol: dict[str, float],
    routes: dict[str, tuple[str, object]],
    conn: sqlite3.Connection,
    seconds: float,
    fail: list[str],
) -> dict[str, float]:
    """Return every name's replayed value, and record every disagreement."""
    got: dict[str, float] = {}
    pending: dict[str, str] = {}

    for name in sorted(routes):
        kind, target = routes[name]
        if kind == "derived":
            pending[name] = str(target)
            continue
        try:
            got[name] = run_sql(conn, f"{label}:{name}", target, seconds)  # type: ignore[arg-type]
        except Fail as e:
            fail.append(str(e))

    # A derived number resolves over the values replayed here, never over the
    # values the agent wrote down.
    while pending:
        progressed = False
        for name in sorted(pending):
            try:
                v = eval_derived(f"{label}:{name}", pending[name], got)
            except KeyError:
                continue
            except Fail as e:
                fail.append(str(e))
                del pending[name]
                progressed = True
                break
            got[name] = v
            del pending[name]
            progressed = True
            break
        if not progressed:
            for name in sorted(pending):
                fail.append(
                    f"{label}:{name}: derived expression {pending[name]!r} cannot be "
                    f"resolved -- it names a number that is undeclared, that failed "
                    f"to replay, or that depends on this one"
                )
            break

    for name in sorted(got):
        claimed = float(rows[name]["value"])
        t = tol[name]
        if not close(claimed, got[name], t):
            fail.append(
                f"{label}:{name}: written as {num(claimed)}, but its own route "
                f"gives {num(got[name])} (diff {abs(claimed - got[name]):.6g}, "
                f"tol {t:g})"
            )
    return got


# ---------------------------------------------------------------------- one task


def check_task(
    root: Path,
    md: Path,
    conn: sqlite3.Connection,
    seconds: float,
    base: str | None,
    head: str | None,
    fail: list[str],
) -> None:
    n = md.stem.split("-", 1)[1]
    try:
        brief = parse_brief(md)
    except Fail as e:
        fail.append(str(e))
        return
    status, tol, n_decl, frame = brief

    if status in SUSPEND_STATUS:
        print(
            f"  TASK-{n} [{status}]: {len(tol)} number(s) declared; "
            f"suspended (replay, agreement, and edit-count not run)"
        )
        return

    task_dir = root / "tasks" / f"TASK-{n}"
    paths = {
        WORKER: task_dir / WORKER,
        VERIFIER: task_dir / VERIFIER,
    }
    present = {k: p for k, p in paths.items() if p.is_file()}

    if not present:
        print(f"  TASK-{n} [{status}]: {len(tol)} number(s) declared, no output yet")
        if status == "closed":
            fail.append(f"TASK-{n}: status is closed but neither output file exists")
        return

    rows: dict[str, dict[str, dict]] = {}
    routes: dict[str, dict[str, tuple[str, object]]] = {}
    replayed_by: dict[str, dict[str, float]] = {}
    for k, p in present.items():
        r = parse_rows(p, tol, fail, n, root)
        if r is None:
            print(f"  TASK-{n} [{status}]: {k} is malformed")
            continue
        rows[k] = r
        routes[k] = {}
        for name in sorted(r):
            try:
                routes[k][name] = route(k, n, name, str(r[name]["query"]).strip(), root)
            except Fail as e:
                fail.append(str(e))
        replayed = replay(k, r, tol, routes[k], conn, seconds, fail)
        replayed_by[k] = replayed
        extra = ""
        if n_decl is not None:
            n_ok = check_declared_n(k, r, n_decl, replayed, fail)
            extra = f", {n_ok}/{len(n_decl)} n declared"
        print(
            f"  TASK-{n} [{status}]: {k} {len(r)} row(s), "
            f"{len(replayed)} replayed{extra}"
        )

    identity_notes: list[str] = []
    for k, replayed in replayed_by.items():
        note = check_period_identity(n, k, tol, replayed, frame, fail)
        if note:
            identity_notes.append(note)
    if identity_notes:
        print(f"  TASK-{n} [{status}]: period identity {identity_notes[0]}")

    # Two agents may share a definition. They may not share an implementation.
    if WORKER in routes and VERIFIER in routes:
        def sqls(which: str) -> dict[Path, str]:
            return {
                t: nm  # type: ignore[misc]
                for nm, (kind, t) in routes[which].items()
                if kind == "sql"
            }
        w, v = sqls(WORKER), sqls(VERIFIER)
        for p in sorted(set(w) & set(v)):
            fail.append(
                f"TASK-{n}: {p.relative_to(root)} backs {w[p]} in {WORKER} and "
                f"{v[p]} in {VERIFIER}; the second computation must be its own"
            )
        fail.extend(cross_side_sql_hash_collisions(n, root, w, v))

    paired = 0
    if WORKER in rows and VERIFIER in rows:
        for name in sorted(set(rows[WORKER]) & set(rows[VERIFIER])):
            w, v = rows[WORKER][name], rows[VERIFIER][name]
            wv, vv, t = float(w["value"]), float(v["value"]), tol[name]
            d = abs(wv - vv)
            if not close(wv, vv, t):
                fail.append(
                    f"TASK-{n}:{name}: worker {num(wv)} and verifier {num(vv)} "
                    f"disagree (diff {d:.6g}, tol {t:g})"
                )
            else:
                paired += 1
            if w["n"] != v["n"]:
                fail.append(
                    f"TASK-{n}:{name}: worker counted n={w['n']} and verifier "
                    f"n={v['n']} over the same corpus"
                )
        print(f"  TASK-{n} [{status}]: {paired}/{len(tol)} number(s) agree")
    else:
        missing = sorted(set(paths) - set(present))
        print(f"  TASK-{n} [{status}]: not comparable yet, waiting on {', '.join(missing)}")

    # How many times were these numbers rewritten after the brief's reset.
    if head:
        try:
            reset = reset_commit(root, head, n)
        except Fail as e:
            fail.append(str(e))
            reset = None
        for k, p in present.items():
            rel = f"tasks/TASK-{n}/{k}"
            try:
                got = commits_touching_since(root, head, rel, reset)
            except Fail as e:
                fail.append(str(e))
                continue
            if len(got) > MAX_ATTEMPTS:
                where = f" since reset {reset[:8]}" if reset else ""
                fail.append(
                    f"TASK-{n}: {k} has been rewritten {len(got)} times{where} "
                    f"(cap is {MAX_ATTEMPTS}: the first and two retries); "
                    f"escalate both sets of numbers instead of trying again"
                )

    # Neither branch may have started from the other's answer.
    if base and head:
        for k, other in ((WORKER, VERIFIER), (VERIFIER, WORKER)):
            rel, orel = f"tasks/TASK-{n}/{k}", f"tasks/TASK-{n}/{other}"
            try:
                sha = first_added(root, f"{base}..{head}", rel)
            except Fail as e:
                fail.append(str(e))
                continue
            if sha is None:
                continue
            if in_tree(root, sha, orel):
                fail.append(
                    f"TASK-{n}: {k} was added in {sha[:8]}, whose tree already held "
                    f"{other}; this branch started from the other answer, so the two "
                    f"computations are not independent"
                )

    if status == "closed":
        for k in sorted(set(paths) - set(present)):
            fail.append(f"TASK-{n}: status is closed but {k} does not exist")
        if WORKER in rows and VERIFIER in rows and paired != len(tol):
            fail.append(
                f"TASK-{n}: status is closed with {paired} of {len(tol)} number(s) "
                f"in agreement"
            )


# ------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--corpus", default="data/corpus_v2.sqlite")
    ap.add_argument("--base-ref", default=None)
    ap.add_argument("--head-ref", default=None)
    ap.add_argument("--sql-seconds", type=float, default=60.0)
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()

    fail: list[str] = []

    # The corpus is the only input. Confirm it is the one the README names.
    corpus = root / args.corpus
    readme = root / "README.md"
    if not corpus.is_file():
        print(f"output_check: FAIL\n  {args.corpus} does not exist; no number can be replayed")
        return 1
    if not readme.is_file():
        print("output_check: FAIL\n  README.md does not exist; the corpus hash is recorded there")
        return 1
    want = README_SHA.search(readme.read_text(encoding="utf-8"))
    if not want:
        print("output_check: FAIL\n  README.md records no sha256 for the corpus")
        return 1
    h = hashlib.sha256()
    with corpus.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != want.group(1):
        print(
            f"output_check: FAIL\n  {args.corpus} is {h.hexdigest()}, "
            f"README.md says {want.group(1)}"
        )
        return 1
    print(f"output_check: corpus {h.hexdigest()[:16]}… matches README.md")

    if args.base_ref and args.head_ref:
        print(f"output_check: history from {args.base_ref}..{args.head_ref}; independence enforced")
    elif args.head_ref:
        print("output_check: no base ref; independence is enforced on the pull request")
    else:
        print("output_check: no refs given; attempts and independence are enforced in CI")

    briefs = sorted((root / "tasks").glob("TASK-*.md")) if (root / "tasks").is_dir() else []
    if not briefs:
        print("output_check: no tasks/TASK-*.md; nothing to check")
        return 0
    print(f"output_check: {len(briefs)} task brief(s)")

    # Plan §4.1: on a pull request, fully check only tasks this diff touches.
    # Untouched tasks (including an open iterating disagreement on main) get a
    # frozen summary and cannot fail this PR. No base ref (push to main) still
    # walks every task.
    touched: frozenset[str] | None = None
    if args.base_ref and args.head_ref:
        try:
            changed = pr_diff_names(root, args.base_ref, args.head_ref)
        except Fail as e:
            print(f"output_check: FAIL\n  {e}")
            return 1
        touched = task_ids_from_paths(changed)
        shown = (
            ", ".join(
                f"TASK-{t}"
                for t in sorted(
                    touched,
                    key=lambda s: (0, int(s)) if s.isdigit() else (1, s),
                )
            )
            or "none"
        )
        print(
            f"output_check: PR {args.base_ref}...{args.head_ref}; "
            f"full-check {shown}; other tasks frozen"
        )

    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    try:
        for md in briefs:
            n = md.stem.split("-", 1)[1]
            if touched is not None and n not in touched:
                frozen_summary(root, md)
                continue
            check_task(root, md, conn, args.sql_seconds, args.base_ref, args.head_ref, fail)
    finally:
        conn.close()

    if args.head_ref:
        recognized = blocked_empty_commits(root, args.head_ref, args.base_ref)
        for sha, subj in recognized:
            print(f"output_check: recognized empty commit {sha[:8]} {subj}")

    if fail:
        print(f"output_check: FAIL ({len(fail)})")
        for f in fail:
            print(f"  {f}")
        return 1
    print("output_check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
