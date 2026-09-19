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

A brief never declares a value. A value in the brief is a value both agents can
copy, and two agents copying one number is not agreement.

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
  brief        exactly one ``status: open|closed`` line; a parseable block.
  shape        top-level list; every row exactly {name, value, n, query}; the
               name set equals the declared set, so a missing number and an
               extra number both fail; no duplicate name; no duplicate query
               within one file.
  route        every SQL path exists, resolves under tasks/TASK-<N>/, and is
               not named by both files: two agents may share a definition but
               not an implementation. A shared *derivation* is allowed, because
               each of its inputs was replayed on its own.
  replay       every number equals what its own route produces, within tol.
               A SQL route whose plan never SCAN/SEARCHes a corpus table
               fails, so two constant SELECTs cannot certify agreement.
  agreement    the two files agree on every value within tol and on every n
               exactly. Any disagreement fails, and both numbers are printed.
  attempts     at most three commits touch one output file: the first and two
               retries. A fourth is not a retry, it is a loop.
  independence (pull requests only) the commit that introduced one agent's file
               did not have the other agent's file in its tree.
  closed       a brief may say ``status: closed`` only when both files are
               present, complete and in full agreement.

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
from pathlib import Path

BLOCK = re.compile(r"^```numbers\s*$(.*?)^```\s*$", re.M | re.S)
STATUS = re.compile(r"^status:[ \t]*(open|closed)[ \t]*$", re.M)
README_SHA = re.compile(r"sha256:\s*`?([0-9a-f]{64})`?")
ROW_KEYS = {"name", "value", "n", "query"}
DERIVED = "derived:"
EPS = 1e-9
MAX_ATTEMPTS = 3
WORKER, VERIFIER = "results.json", "mine.json"

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


def first_added(root: Path, rng: str, path: str) -> str | None:
    """The earliest commit in ``rng`` that added ``path``, if any."""
    out = git(root, "log", rng, "--diff-filter=A", "--format=%H", "--", path)
    shas = [l.strip() for l in out.splitlines() if l.strip()]
    return shas[-1] if shas else None


# ------------------------------------------------------------------------- brief


def parse_brief(md: Path) -> tuple[str, dict[str, float]]:
    text = md.read_text(encoding="utf-8")

    st = STATUS.findall(text)
    if len(st) != 1:
        raise Fail(
            f"{md.name}: needs exactly one line 'status: open' or "
            f"'status: closed'; found {len(st)}"
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
    return st[0], tol


def parse_rows(path: Path, tol: dict[str, float], fail: list[str]) -> dict[str, dict] | None:
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

    seen: dict[str, str] = {}
    for name, r in rows.items():
        q = str(r["query"]).strip()
        if not q:
            fail.append(f"{path.name}:{name}: query is empty")
            ok = False
            continue
        if q in seen:
            fail.append(
                f"{path.name}:{name}: query {q!r} already backs {seen[q]}; "
                f"one route may produce only one number"
            )
            ok = False
        seen[q] = name

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


def run_sql(conn: sqlite3.Connection, label: str, sql_path: Path, seconds: float) -> float:
    stmts = strip_and_split(sql_path.read_text(encoding="utf-8"))
    if len(stmts) != 1:
        raise Fail(f"{label}: {sql_path.name} holds {len(stmts)} statements; it must hold exactly one")
    stmt = stmts[0]
    if not re.match(r"(?is)^\s*(select|with)\b", stmt):
        raise Fail(f"{label}: {sql_path.name} must begin with SELECT or WITH")

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
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 100_000)
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
        raise Fail(f"{label}: {sql_path.name} returned {len(got[0])} columns; it must return exactly one")
    v = got[0][0]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Fail(f"{label}: {sql_path.name} returned {v!r}, which is not a number")
    return float(v)


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
        status, tol = parse_brief(md)
    except Fail as e:
        fail.append(str(e))
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
    for k, p in present.items():
        r = parse_rows(p, tol, fail)
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
        print(f"  TASK-{n} [{status}]: {k} {len(r)} row(s), {len(replayed)} replayed")

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

    # How many times were these numbers rewritten.
    if head:
        for k, p in present.items():
            rel = f"tasks/TASK-{n}/{k}"
            try:
                got = commits_touching(root, head, rel)
            except Fail as e:
                fail.append(str(e))
                continue
            if len(got) > MAX_ATTEMPTS:
                fail.append(
                    f"TASK-{n}: {k} has been rewritten {len(got)} times "
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

    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    try:
        for md in briefs:
            check_task(root, md, conn, args.sql_seconds, args.base_ref, args.head_ref, fail)
    finally:
        conn.close()

    if fail:
        print(f"output_check: FAIL ({len(fail)})")
        for f in fail:
            print(f"  {f}")
        return 1
    print("output_check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
