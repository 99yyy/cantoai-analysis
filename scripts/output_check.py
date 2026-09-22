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
                                 (the tables gate_config.json lists)
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
               edit-count for that task (plan §4.4). An optional
               ``corpus_sha:`` line (plan §4.5) holds the README pin at
               close; at most one, 64-char lowercase hex. An optional fenced
               ``n`` block (plan §2.5), ``frame`` block (plan §6 identity),
               and ``identities`` block (``<expr> = <expr>  <tol>`` over
               replayed SQL-routed names) are parsed here; they are not
               required of every brief.
               Briefs are the top-level glob ``tasks/TASK-*.md`` (not
               recursive). A ``results.json`` or ``mine.json`` under any
               TASK-N directory whose matching ``tasks/TASK-N.md`` is not in
               that glob fails: hiding the brief must not make this script a
               no-op exit 0 (plan §2.6).
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
  identity     a fenced ``identities`` block lists ``<expr> = <expr>  <tol>``
               lines, evaluated with the same AST as ``derived:`` over this
               file's **replayed** values (never the values the agent wrote,
               and never a merge of worker+verifier dicts). ``frame.<field>``
               binds a numeric ``frame`` entry. An identity **counts only
               when every declared name in it is a SQL route in the file
               under check**; otherwise it is skipped. A derived name would
               make ``a + b = a + b`` a tautology on that file. An identity
               skipped on both sides was never checked: on an ``open`` task
               that fails; a task closed before the rule prints a note.
               A ``derived:`` route must name at least one declared number.
  attempts     at most three commits touch one output file after the
               latest brief revision (the reset commit): the first and two
               retries. A fourth is not a retry, it is a loop. Recount
               starts from that reset, so reopen after a brief edit does
               not inherit the previous ceiling (plan §4.4).
  independence (pull requests only) the commit that introduced one agent's file
               did not have the other agent's file in its tree, nor did any
               ancestor of that commit; the two introducing commits have no
               ancestor relationship, were not both introduced on this branch,
               and do not share an author identity (plan §2.7).
  blocked-commit
               an empty commit whose subject starts with ``BLOCKED:`` is
               recognized and printed. It is the durable marker when the
               agent cannot edit the brief; the tree equals the parent, so
               merge still leaves a git-log trace (plan §4.4).
  closed       a brief may say ``status: closed`` only when both files are
               present, complete and in full agreement. Close also stamps
               ``corpus_sha:`` with the then-current README pin. A closed
               brief whose stamp is missing or differs from the current
               corpus sha is STALE: replay, agreement, and edit-count are
               skipped, the task does not participate in red/green, and
               this script does not print ``N/N number(s) agree`` (plan
               §4.5). Keep rate must not copy a STALE line. A corpus
               change is a ``repair/`` PR that updates README and the
               stamps together; a live closed task (stamp matches) still
               replays against the new pin.
  result       ``tasks/TASK-N/RESULT.json`` is the auditor's round outcome,
               not a worker/verifier file. ``subtype`` is the machine
               ending; ``verdict`` is the research judgement and is
               non-null only when subtype is success. Success does not
               mean the hypothesis is supported. When the file exists on a
               closed/escalated/blocked task, the schema is enforced and
               mismatched machine fields fail: success requires both
               outputs, pairwise agreement within tol, and a live closed
               brief; out_of_turns requires the post-reset rewrite count
               to be at cap; corpus_sha must equal the README pin.
               ``turns_used`` must equal ``len(tasks/TASK-N/launches.json)``
               for that task: a repo-local ledger of ``{id, role, at}``
               records the coordinator or auditor appends (worker/verifier
               do not invent launches). Family total is the sum of those
               lengths over the root and its ``-b`` / ``-c`` siblings, and
               must be ``<= 16``. A RESULT whose subtype is not
               ``out_of_budget`` or ``blocked`` fails when the family is
               above the cap; ``out_of_budget`` fails when the family is
               below it. A parent RESULT is not re-judged for later family
               growth after a child brief exists (parent RESULT is
               immutable). ``cost_usd`` / ``budget_usd`` /
               ``val_iterations`` are forbidden. Missing RESULT on a task
               already terminal is transitional; a PR that newly sets a
               terminal status must include the file. Present on ``open``
               fails. ``fork_depth`` is at most 2. A letter-suffix brief
               must set ``forked_from`` / ``fork_depth`` to the parent id
               and parent depth + 1; a root RESULT keeps both at null / 0.
  fork         a brief ``tasks/TASK-N-b.md`` (then ``-c``) is a sibling of
               ``TASK-N``, not a new measured target. The ``numbers`` and
               ``n`` fences (and ``frame`` / ``identities`` when present)
               must be byte-identical to the immediate parent. Changing a
               tolerance is a new task, not a fork. The child adds
               ``## Prior Attempts`` quoting the parent RESULT. The parent
               stays terminal and its RESULT.json is never edited or
               deleted after the child brief is added. Depth 1 = ``-b``,
               depth 2 = ``-c``. Opening ``-d`` (depth 3) is blocked, not
               a third fork. A fork is allowed only when the parent
               RESULT is ``verdict: refuted`` or ``subtype: out_of_turns``.
               The Grok Bot ``check-brief`` skill is not this check.
  scope        (pull requests only) only a task whose brief or files under
               ``tasks/TASK-N/`` appear in the PR diff is fully checked.
               Other tasks print a frozen summary and cannot fail the PR:
               an ``open`` iterating task on main must not redden an
               unrelated one (plan §4.1). Touching either output file
               re-runs the comparison (plan §4.3). On main, every task is
               still fully checked.

On independence, precisely: the introducing-commit *tree* check only blocked
the naive order (merge the other side, then commit yours). Committing yours
first and then merging main, or writing both sides on one branch across
commits that delete-and-restore, left that tree clean. Plan §2.7 walks every
ancestor, requires the two introducing commits to be incomparable in the DAG,
rejects both files being first-added on this pull request, and rejects a
shared author identity. That still does not prove the agent never fetched the
other branch mid-run -- nothing in CI can, and the auditor reads the history
for it. Launch both agents from one starting ref, with distinct authors, and
the check passes for both.

Usage:
    python scripts/output_check.py [--repo-root .]
                                   [--base-ref origin/main --head-ref HEAD]
                                   [--task N]
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
IDENTITIES_FENCE = re.compile(r"^```identities\s*$(.*?)^```\s*$", re.M | re.S)
STATUS = re.compile(
    r"^status:[ \t]*(open|closed|escalated|blocked)[ \t]*$", re.M
)
# Close stamps the README pin (plan §4.5). Missing or mismatched on a
# closed brief is STALE, not a parse error; a malformed value is a parse error.
CORPUS_SHA_LINE = re.compile(r"^corpus_sha:[ \t]*(.*)$", re.M)
CORPUS_SHA_VALUE = re.compile(r"^`?([0-9a-f]{64})`?$")
README_SHA = re.compile(r"sha256:\s*`?([0-9a-f]{64})`?")
ROW_KEYS = {"name", "value", "n", "query"}
DERIVED = "derived:"
EPS = 1e-9
MAX_ATTEMPTS = 3


class Fail(Exception):
    """A condition this script exists to catch."""


GATE_CONFIG_NAME = "gate_config.json"


def load_gate_config() -> dict:
    """Project facts the gate reads (tables, sides, number families, ...).

    Looked up next to this file first: CI copies the base branch's config
    beside the base branch's gate scripts in ``/tmp/gate``, so a pull request
    is judged by the base's config, not its own. ``scripts/gate_config.json``
    under the current directory is the fallback for a base branch that had
    no config yet.
    """
    here = Path(__file__).resolve().parent / GATE_CONFIG_NAME
    cwd = Path.cwd() / "scripts" / GATE_CONFIG_NAME
    for cand in (here, cwd):
        if cand.is_file():
            try:
                cfg = json.loads(cand.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise Fail(f"{cand}: not valid JSON: {e}") from e
            for key in ("corpus", "pin_file", "sides", "tables", "unit_table", "families"):
                if key not in cfg:
                    raise Fail(f"{cand}: missing key {key!r}")
            if cfg["unit_table"] not in cfg["tables"]:
                raise Fail(f"{cand}: unit_table {cfg['unit_table']!r} is not in tables")
            return cfg
    raise Fail(f"{GATE_CONFIG_NAME} not found beside {__file__} or under ./scripts/")


GATE_CONFIG = load_gate_config()
CORPUS_PATH_DEFAULT = str(GATE_CONFIG["corpus"])
PIN_FILE = str(GATE_CONFIG["pin_file"])
WORKER = str(GATE_CONFIG["sides"]["worker"])
VERIFIER = str(GATE_CONFIG["sides"]["verifier"])
RESULT = "RESULT.json"
LAUNCHES = "launches.json"
SUSPEND_STATUS = frozenset({"escalated", "blocked"})
TERMINAL_STATUS = frozenset({"closed", "escalated", "blocked"})
# Auditor-written round outcome. Worker/verifier never write this file.
# turns_used is Cloud Agent launch count and equals len(launches.json) for
# that task. The family (root + -b + -c) shares LAUNCH_BUDGET. Rewrite
# counts (cap MAX_ATTEMPTS) still decide subtype out_of_turns.
RESULT_KEYS = (
    "task",
    "subtype",
    "verdict",
    "hypothesis",
    "why",
    "numbers",
    "turns_used",
    "turn_cap",
    "corpus_sha",
    "forked_from",
    "fork_depth",
)
RESULT_KEY_SET = frozenset(RESULT_KEYS)
RESULT_NUMBER_KEYS = frozenset({"value", "within_tol"})
SUBTYPES = frozenset(
    {
        "success",
        "out_of_turns",
        "out_of_budget",
        "blocked",
        "infra_failure",
        "stale",
    }
)
VERDICTS = frozenset({"supported", "refuted", "inconclusive"})
FORBIDDEN_RESULT_FIELDS = ("cost_usd", "budget_usd", "val_iterations")
LAUNCH_BUDGET = 16
LAUNCH_RECORD_KEYS = ("id", "role", "at")
LAUNCH_RECORD_KEY_SET = frozenset(LAUNCH_RECORD_KEYS)
LAUNCH_ROLES = frozenset(
    {"worker", "verifier", "auditor", "repair", "coordinator"}
)
BUDGET_STOP_SUBTYPES = frozenset({"out_of_budget", "blocked"})
BLOCKED_SUBJECT_PREFIX = "BLOCKED:"
# tasks/TASK-N.md or anything under tasks/TASK-N/ (plan §4.1 / §4.3).
TASK_PATH_RE = re.compile(r"^tasks/TASK-([^/]+)(?:\.md|/)")
# A TASK-N directory name anywhere under tasks/ (plan §2.6 orphan outputs).
TASK_DIR_NAME = re.compile(r"^TASK-(.+)$")
# Letter-suffix forks: TASK-6, TASK-6-b, TASK-6-c. Depth 3 would be -d.
TASK_ID_RE = re.compile(r"^(\d+)(?:-([a-z]))?$")
FORKED_FROM_RE = re.compile(r"^TASK-\d+(?:-[bc])?$")
MAX_FORK_DEPTH = 2
FORK_LETTER = {1: "b", 2: "c"}
FORK_DEPTH = {"b": 1, "c": 2}
FORK_FENCES = ("numbers", "n", "frame", "identities")
PRIOR_ATTEMPTS_RE = re.compile(r"^## Prior Attempts[ \t]*$", re.M)
FORK_TRIGGER_VERDICT = "refuted"
FORK_TRIGGER_SUBTYPE = "out_of_turns"

ALLOWED_BINOP = (ast.Add, ast.Sub, ast.Mult, ast.Div)
ALLOWED_UNARY = (ast.UAdd, ast.USub)

# Real corpus tables. SCAN CONSTANT ROW / sqlite_master / a CTE of the same
# name is not a touch. SQLite prints aliases (SCAN v), so aliases from FROM/JOIN
# are resolved before the name is checked.
CORPUS_TABLES = frozenset(GATE_CONFIG["tables"]) | frozenset(
    GATE_CONFIG.get("other_tables", [])
)
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


class Identity(NamedTuple):
    """One ``<left> = <right>  <tol>`` line from an ``identities`` fence."""

    left: str
    right: str
    tol: float
    line: str


class Brief(NamedTuple):
    """Parsed task brief. ``n_decl`` is None when the brief has no ``n`` fence.

    ``corpus_sha`` is None when the brief has no ``corpus_sha:`` line.
    ``identities`` is empty when the brief has no ``identities`` fence.
    """

    status: str
    tol: dict[str, float]
    n_decl: dict[str, str] | None
    frame: dict[str, float]
    corpus_sha: str | None
    identities: tuple[Identity, ...]


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


def is_ancestor(root: Path, maybe_anc: str, desc: str) -> bool:
    """True when ``maybe_anc`` equals ``desc`` or is an ancestor of it."""
    p = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", maybe_anc, desc],
        capture_output=True,
        text=True,
    )
    if p.returncode == 0:
        return True
    if p.returncode == 1:
        return False
    raise Fail(
        f"git merge-base --is-ancestor {maybe_anc} {desc}: "
        f"{p.stderr.strip() or 'failed'}"
    )


def commit_author(root: Path, sha: str) -> str:
    """Author identity of ``sha`` as ``Name <email>``."""
    ident = git(root, "log", "-1", "--format=%an <%ae>", sha).strip()
    if not ident or ident == "<>":
        raise Fail(f"{sha}: git author is empty")
    return ident


def check_independence(
    root: Path, n: str, base: str, head: str, fail: list[str]
) -> None:
    """Plan §2.7: the two introducing commits are independent.

    A file first-added in ``base..head`` may not have the other side in its
    own tree *or in any ancestor tree*. When both sides have an introducing
    commit and this pull request introduced at least one of them, those
    commits must have no ancestor relationship, must not both be unique to
    this pull request (same branch), and must not share an author identity.
    """
    intro: dict[str, str] = {}
    added_in_pr: dict[str, bool] = {}
    for k in (WORKER, VERIFIER):
        rel = f"tasks/TASK-{n}/{k}"
        try:
            sha_pr = first_added(root, f"{base}..{head}", rel)
        except Fail as e:
            fail.append(str(e))
            continue
        if sha_pr is not None:
            intro[k] = sha_pr
            added_in_pr[k] = True
            continue
        try:
            if not in_tree(root, head, rel):
                continue
            sha_all = first_added(root, head, rel)
        except Fail as e:
            fail.append(str(e))
            continue
        if sha_all is not None:
            intro[k] = sha_all
            added_in_pr[k] = False

    for k, other in ((WORKER, VERIFIER), (VERIFIER, WORKER)):
        sha = intro.get(k)
        if sha is None or not added_in_pr.get(k):
            continue
        orel = f"tasks/TASK-{n}/{other}"
        try:
            held = first_added(root, sha, orel)
        except Fail as e:
            fail.append(str(e))
            continue
        if held is not None:
            fail.append(
                f"TASK-{n}: {k} was added in {sha[:8]}, whose history already "
                f"held {other} (at {held[:8]}); the two computations are not "
                f"independent"
            )

    w, v = intro.get(WORKER), intro.get(VERIFIER)
    if not (w and v):
        return
    if not (added_in_pr.get(WORKER) or added_in_pr.get(VERIFIER)):
        return

    try:
        related = is_ancestor(root, w, v) or is_ancestor(root, v, w)
    except Fail as e:
        fail.append(str(e))
        related = False
    if related:
        fail.append(
            f"TASK-{n}: {WORKER} introduced in {w[:8]} and {VERIFIER} "
            f"introduced in {v[:8]} have an ancestor relationship; "
            f"the two computations are not independent"
        )

    if added_in_pr.get(WORKER) and added_in_pr.get(VERIFIER):
        fail.append(
            f"TASK-{n}: {WORKER} and {VERIFIER} were both introduced on this "
            f"branch ({w[:8]}, {v[:8]}); the two computations are not "
            f"independent"
        )

    try:
        aw = commit_author(root, w)
        av = commit_author(root, v)
    except Fail as e:
        fail.append(str(e))
        return
    if aw == av:
        fail.append(
            f"TASK-{n}: {WORKER} introduced in {w[:8]} and {VERIFIER} "
            f"introduced in {v[:8]} have the same author {aw}; "
            f"the two computations are not independent"
        )


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


def discover_briefs(root: Path) -> list[Path]:
    """Top-level ``tasks/TASK-*.md`` only. The glob is not recursive (plan §2.6)."""
    tasks = root / "tasks"
    if not tasks.is_dir():
        return []
    return sorted(p for p in tasks.glob("TASK-*.md") if p.is_file())


def brief_task_id(md: Path) -> str:
    return md.stem.split("-", 1)[1]


class ForkId(NamedTuple):
    """Filename fork identity. ``letter`` is None on a root TASK-N."""

    root: str
    letter: str | None
    depth: int
    task: str
    parent: str | None


def parse_fork_id(n: str) -> ForkId | None:
    """Parse ``6``, ``6-b``, ``6-c``, or ``6-d``. None if not that shape."""
    m = TASK_ID_RE.fullmatch(n)
    if not m:
        return None
    root, letter = m.group(1), m.group(2)
    if letter is None:
        return ForkId(root, None, 0, n, None)
    depth = FORK_DEPTH.get(letter)
    if depth is None:
        guessed = ord(letter) - ord("a")
        return ForkId(root, letter, guessed, n, None)
    parent = root if depth == 1 else f"{root}-{FORK_LETTER[depth - 1]}"
    return ForkId(root, letter, depth, n, parent)


def child_task_id(fid: ForkId) -> str | None:
    """Next letter-suffix id, or None when that would exceed ``MAX_FORK_DEPTH``."""
    nxt = fid.depth + 1
    if nxt > MAX_FORK_DEPTH or nxt not in FORK_LETTER:
        return None
    return f"{fid.root}-{FORK_LETTER[nxt]}"


def family_member_ids(n: str) -> tuple[str, ...]:
    """Root + ``-b`` + ``-c`` ids that share one launch budget."""
    fid = parse_fork_id(n)
    root = fid.root if fid is not None else n
    return (root, f"{root}-b", f"{root}-c")


def has_letter_child_brief(root: Path, n: str) -> bool:
    """True when a deeper letter-suffix brief exists (parent RESULT is frozen)."""
    fid = parse_fork_id(n)
    if fid is None:
        return False
    child = child_task_id(fid)
    if child is None:
        return False
    return (root / "tasks" / f"TASK-{child}.md").is_file()


def normalize_task_id(raw: str) -> str:
    """``6`` or ``TASK-6`` → ``6``. Empty or path-like values fail."""
    s = raw.strip()
    if s.upper().startswith("TASK-"):
        s = s.split("-", 1)[1]
    if not s or "/" in s or "\\" in s or s in {".", ".."}:
        raise Fail(f"task id {raw!r} is not a TASK-N id")
    return s


def filter_briefs(briefs: list[Path], task: str | None) -> list[Path]:
    """All briefs, or exactly the named TASK-N brief."""
    if task is None:
        return briefs
    n = normalize_task_id(task)
    picked = [md for md in briefs if brief_task_id(md) == n]
    if not picked:
        raise Fail(f"no tasks/TASK-{n}.md")
    return picked


def task_id_from_output_path(path: Path, tasks_root: Path) -> str | None:
    """TASK-N id for an output file, or None if it is not under a TASK-N dir."""
    try:
        rel = path.relative_to(tasks_root)
    except ValueError:
        return None
    for part in rel.parts[:-1]:
        m = TASK_DIR_NAME.fullmatch(part)
        if m:
            return m.group(1)
    return None


def output_files_by_task(root: Path) -> dict[str, list[Path]]:
    """``results.json`` / ``mine.json`` / ``RESULT.json`` under a TASK-N directory."""
    tasks = root / "tasks"
    found: dict[str, list[Path]] = {}
    if not tasks.is_dir():
        return found
    for name in (WORKER, VERIFIER, RESULT):
        for path in tasks.rglob(name):
            if not path.is_file():
                continue
            n = task_id_from_output_path(path, tasks)
            if n is None:
                continue
            found.setdefault(n, []).append(path)
    return found


def orphan_output_message(n: str, rel: str) -> str:
    return (
        f"TASK-{n}: {rel} exists but the matching brief "
        f"tasks/TASK-{n}.md cannot be found"
    )


def orphan_output_messages(root: Path, briefs: list[Path]) -> list[str]:
    """Outputs whose matching top-level brief is not in ``briefs`` (plan §2.6)."""
    known = {brief_task_id(md) for md in briefs}
    msgs: list[str] = []
    by_task = output_files_by_task(root)
    for n in sorted(
        by_task,
        key=lambda s: (0, int(s)) if s.isdigit() else (1, s),
    ):
        if n in known:
            continue
        files = sorted(
            {p.resolve() for p in by_task[n]},
            key=lambda p: p.as_posix(),
        )
        for p in files:
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                rel = p.as_posix()
            msgs.append(orphan_output_message(n, rel))
    return msgs


def stale_closed(status: str, stamp: str | None, corpus_sha: str) -> bool:
    """True when a closed brief's stamp is missing or not the current pin."""
    return status == "closed" and stamp != corpus_sha


def stale_closed_line(n: str, stamp: str | None, corpus_sha: str) -> str:
    """The STALE skip line. Must not contain ``number(s) agree`` (plan §4.5)."""
    shown = stamp if stamp is not None else "missing"
    return (
        f"  TASK-{n} [closed]: STALE; stamp {shown} != README sha256 "
        f"{corpus_sha}; replay skipped"
    )


def frozen_summary(root: Path, md: Path, corpus_sha: str) -> None:
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
    extra = ""
    if brief.status in SUSPEND_STATUS:
        extra = "; suspended"
    elif stale_closed(brief.status, brief.corpus_sha, corpus_sha):
        extra = "; STALE"
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

    frame = parse_frame_block(md.name, text)
    return Brief(
        st[0],
        tol,
        n_decl,
        frame,
        parse_corpus_sha(md.name, text),
        parse_identities_block(md.name, text, tol, frame),
    )


def parse_corpus_sha(label: str, text: str) -> str | None:
    """The close stamp, or None when the brief has no ``corpus_sha:`` line.

    More than one line, or a value that is not 64-char lowercase hex (optional
    backticks), is a parse error. A missing line on a closed brief is STALE
    later, not a parse error (plan §4.5).
    """
    found = CORPUS_SHA_LINE.findall(text)
    if len(found) > 1:
        raise Fail(
            f"{label}: corpus_sha appears {len(found)} times; at most one line"
        )
    if not found:
        return None
    raw = found[0].strip()
    m = CORPUS_SHA_VALUE.fullmatch(raw)
    if not m:
        raise Fail(
            f"{label}: corpus_sha is not a 64-char lowercase hex sha256: {raw!r}"
        )
    return m.group(1)


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

    Predicate lines (``<table>.<column> <sql>``) are not numeric entries; see
    ``parse_frame_predicates``. Identities bind ``frame.<field>`` to these.
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


FRAME_PREDICATE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$")


def parse_frame_predicates(label: str, text: str) -> list[tuple[str, str, str]]:
    """``<table>.<column> <sql-fragment>`` lines of the ``frame`` fence.

    These define the published set: a row of ``table`` is published when
    ``column <sql-fragment>`` holds (``windows.tier IN ('A','B')``). Numeric
    entries are not predicates. A fragment may not contain ``;`` or a SQL
    comment. Returns (table, column, fragment) in file order; [] without a
    fence.
    """
    m = FRAME_FENCE.search(text)
    if not m:
        return []
    out: list[tuple[str, str, str]] = []
    for raw in m.group(1).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) == 2:
            try:
                float(parts[1])
                continue
            except ValueError:
                pass
        pm = FRAME_PREDICATE.match(line)
        if not pm:
            continue
        table, column, frag = pm.group(1), pm.group(2), pm.group(3).strip()
        if ";" in frag or "--" in frag or "/*" in frag:
            raise Fail(f"{label}: frame predicate {line!r} may not contain ';' or a comment")
        out.append((table, column, frag))
    return out


def _identity_fail_expr(label: str) -> Fail:
    return Fail(
        f"{label}: a derived expression may use only declared names, "
        f"numbers, + - * / and parentheses"
    )


def _walk_identity_node(
    node: ast.AST, names: set[str], frame_fields: set[str], label: str
) -> None:
    """Collect declared-name ids and ``frame.<field>`` attrs; reject the rest."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return
    if isinstance(node, ast.Name):
        names.add(node.id)
        return
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "frame":
            frame_fields.add(node.attr)
            return
        raise _identity_fail_expr(label)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ALLOWED_UNARY):
        _walk_identity_node(node.operand, names, frame_fields, label)
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, ALLOWED_BINOP):
        _walk_identity_node(node.left, names, frame_fields, label)
        _walk_identity_node(node.right, names, frame_fields, label)
        return
    raise _identity_fail_expr(label)


def parse_identity_expr(label: str, expr: str) -> tuple[set[str], set[str]]:
    """Return (declared-name ids, frame field names) for one identity side."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise Fail(f"{label}: derived expression does not parse: {e.msg}") from e
    names: set[str] = set()
    frame_fields: set[str] = set()
    _walk_identity_node(tree.body, names, frame_fields, label)
    return names, frame_fields


def parse_identities_block(
    label: str,
    text: str,
    declared: dict[str, float],
    frame: dict[str, float],
) -> tuple[Identity, ...]:
    """``<expr> = <expr>  <tol>`` lines. Empty tuple when there is no fence.

    Every name must be in the numbers block. ``frame.<field>`` must be a
    numeric entry of the ``frame`` fence. The fence is optional; when it is
    present it must not be empty.
    """
    m = IDENTITIES_FENCE.search(text)
    if not m:
        return ()
    out: list[Identity] = []
    for raw in m.group(1).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.rsplit(None, 1)
        if len(parts) != 2:
            raise Fail(
                f"{label}: identities line is not '<expr> = <expr>  <tol>': {line!r}"
            )
        eq, tol_raw = parts
        try:
            t = float(tol_raw)
        except ValueError:
            raise Fail(
                f"{label}: identities line has a non-numeric tolerance {tol_raw!r}"
            )
        if t < 0:
            raise Fail(f"{label}: identities line has a negative tolerance {t}")
        if eq.count("=") != 1:
            raise Fail(
                f"{label}: identities line is not '<expr> = <expr>  <tol>': {line!r}"
            )
        left, right = (p.strip() for p in eq.split("=", 1))
        if not left or not right:
            raise Fail(
                f"{label}: identities line is not '<expr> = <expr>  <tol>': {line!r}"
            )
        tag = f"{label}:identities"
        for expr in (left, right):
            names, fields = parse_identity_expr(tag, expr)
            extra = sorted(names - set(declared))
            if extra:
                raise Fail(
                    f"{label}: identities names {extra[0]!r} which is not "
                    f"in the numbers block"
                )
            missing_frame = sorted(f for f in fields if f not in frame)
            if missing_frame:
                raise Fail(
                    f"{label}: identities names frame.{missing_frame[0]} "
                    f"which is not in the frame block"
                )
        out.append(Identity(left, right, t, line))
    if not out:
        raise Fail(f"{label}: the identities block is empty")
    return tuple(out)


def fence_interior(text: str, kind: str) -> str | None:
    """Raw interior of a fenced block, or None when that fence is absent.

    Byte identity of a fork compares this string, including comments and
    whitespace. The opening fence line's trailing spaces are not part of it.
    """
    regex = {
        "numbers": BLOCK,
        "n": N_FENCE,
        "frame": FRAME_FENCE,
        "identities": IDENTITIES_FENCE,
    }.get(kind)
    if regex is None:
        raise Fail(f"unknown fence kind {kind!r}")
    m = regex.search(text)
    return m.group(1) if m else None


def prior_attempts_section(text: str) -> str | None:
    """Body after ``## Prior Attempts`` until the next ``## `` heading."""
    m = PRIOR_ATTEMPTS_RE.search(text)
    if not m:
        return None
    rest = text[m.end() :]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


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


def identity_sql_routed(
    names: set[str],
    declared: dict[str, float],
    routes: dict[str, tuple[str, object]],
) -> bool:
    """True when every declared name in ``names`` is a SQL route in this file.

    Per-file: ``routes`` is one agent's map. Do not merge worker and verifier.
    An identity with no declared names does not count.
    """
    declared_names = [nm for nm in names if nm in declared]
    if not declared_names:
        return False
    return all(routes.get(nm, (None, None))[0] == "sql" for nm in declared_names)


def identity_unchecked_on_both_sides(
    task_n: str,
    status: str,
    identities: tuple[Identity, ...],
    worker_skipped: set[str],
    verifier_skipped: set[str],
    fail: list[str],
) -> list[str]:
    """An identity skipped in both files was never checked anywhere.

    Each side skips an identity when it routes one of its names as
    ``derived:``. Two sides that both do so turn the line into a tautology on
    both, and the brief's bar is unenforced. On an ``open`` task that is a
    failure the agents must fix (route the name as SQL on at least one side).
    A task already ``closed`` when the rule landed keeps its close; the line is
    printed so the audit can see which of its identities never ran. Returns
    the printed lines.
    """
    both = [i.line for i in identities if i.line in worker_skipped and i.line in verifier_skipped]
    if not both:
        return []
    out: list[str] = []
    for line in both:
        msg = (
            f"identity {line} is checked on neither side "
            f"({WORKER} and {VERIFIER} both route a name in it as derived:)"
        )
        if status == "closed":
            out.append(f"{msg}; closed before this rule, not failed")
        else:
            fail.append(f"TASK-{task_n}: {msg}")
            out.append(msg)
    return out


def check_identities(
    task_n: str,
    label: str,
    identities: tuple[Identity, ...],
    declared: dict[str, float],
    replayed: dict[str, float],
    routes: dict[str, tuple[str, object]],
    frame: dict[str, float],
    fail: list[str],
) -> tuple[list[str], list[str]]:
    """Evaluate ``identities`` over this file's replayed values only.

    An identity counts only when every declared name in it is a SQL route in
    ``routes``. Otherwise skip (a derived name would make the line a
    tautology). Returns (held notes, skipped lines).
    """
    held: list[str] = []
    skipped: list[str] = []
    for ident in identities:
        try:
            left_names, _ = parse_identity_expr(f"{label}:identity", ident.left)
            right_names, _ = parse_identity_expr(f"{label}:identity", ident.right)
        except Fail as e:
            fail.append(f"TASK-{task_n}: {label}: {e}")
            continue
        names = left_names | right_names
        if not identity_sql_routed(names, declared, routes):
            skipped.append(ident.line)
            continue
        missing = [nm for nm in sorted(names) if nm not in replayed]
        if missing:
            skipped.append(ident.line)
            continue
        try:
            left_v = eval_derived(
                f"{label}:identity", ident.left, replayed, frame
            )
            right_v = eval_derived(
                f"{label}:identity", ident.right, replayed, frame
            )
        except KeyError as e:
            fail.append(
                f"TASK-{task_n}: {label}: identity {ident.left} = {ident.right} "
                f"cannot be resolved ({e.args[0]})"
            )
            continue
        except Fail as e:
            fail.append(f"TASK-{task_n}: {label}: {e}")
            continue
        if not close(left_v, right_v, ident.tol):
            fail.append(
                f"TASK-{task_n}: {label}: identity {ident.left} = {ident.right} "
                f"-> {num(left_v)} = {num(right_v)} does not hold "
                f"(tol {ident.tol:g})"
            )
            continue
        held.append(
            f"{ident.left} = {ident.right} -> {num(left_v)} = {num(right_v)}"
        )
    return held, skipped


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
    """True when EXPLAIN QUERY PLAN SCAN/SEARCHes a configured corpus table."""
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
            f"a corpus table ({', '.join(sorted(CORPUS_TABLES))}); plan: {plan_txt}"
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


def eval_derived(
    label: str,
    expr: str,
    known: dict[str, float],
    frame: dict[str, float] | None = None,
) -> float:
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
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "frame"
                and frame is not None
                and node.attr in frame
            ):
                return frame[node.attr]
            raise Fail(
                f"{label}: a derived expression may use only declared names, "
                f"numbers, + - * / and parentheses"
            )
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
        names, _fields = parse_identity_expr(f"{label}:{name}", expr)
        if not names:
            raise Fail(
                f"{label}:{name}: derived: {expr!r} names no declared number; "
                f"a constant is not a route"
            )
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


# ---------------------------------------------------------------- RESULT.json


def is_nonneg_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def is_finite_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def status_at(root: Path, rev: str, n: str) -> str | None:
    """Brief status at ``rev``, or None if the brief is missing or unparsable."""
    rel = f"tasks/TASK-{n}.md"
    if not in_tree(root, rev, rel):
        return None
    try:
        text = git(root, "show", f"{rev}:{rel}")
    except Fail:
        return None
    found = STATUS.findall(text)
    if len(found) != 1:
        return None
    return found[0]


def newly_stopped(
    root: Path, n: str, base: str | None, head: str | None, status_now: str
) -> bool:
    """True when this PR takes the brief from non-terminal to terminal.

    Transitional: a task already closed/escalated/blocked (TASK-6) is not
    required to grow ``RESULT.json``. Main (no ``--base-ref``) does not
    require a missing file either.
    """
    if not base or not head:
        return False
    if status_now not in TERMINAL_STATUS:
        return False
    old = status_at(root, base, n)
    if old in TERMINAL_STATUS:
        return False
    return True


def round_reset_for_result(
    root: Path, rev: str, n: str, status: str
) -> str | None:
    """Brief commit that starts the round RESULT's rewrite count talks about.

    Open: the latest brief revision (same as ``reset_commit``). Terminal:
    the latest brief commit whose status was ``open``, so the stop itself
    (a brief edit) does not zero the count. No open brief in history:
    count every output commit.
    """
    got = commits_touching(root, rev, f"tasks/TASK-{n}.md")
    if not got:
        return None
    if status not in TERMINAL_STATUS:
        return got[0]
    for sha in got:
        if status_at(root, sha, n) == "open":
            return sha
    return None


def max_output_rewrites(root: Path, rev: str, n: str, status: str) -> int:
    """Max worker/verifier rewrite count after the round reset (exclusive)."""
    since = round_reset_for_result(root, rev, n, status)
    counts: list[int] = []
    for k in (WORKER, VERIFIER):
        rel = f"tasks/TASK-{n}/{k}"
        counts.append(len(commits_touching_since(root, rev, rel, since)))
    return max(counts) if counts else 0


def load_output_pairs(path: Path) -> dict[str, tuple[float, int]] | None:
    """``name -> (value, n)`` from a worker/verifier file, or None if unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, list):
        return None
    out: dict[str, tuple[float, int]] = {}
    for row in data:
        if not isinstance(row, dict):
            return None
        name = row.get("name")
        value = row.get("value")
        counted = row.get("n")
        if not isinstance(name, str) or name in out:
            return None
        if not is_finite_number(value) or not is_nonneg_int(counted):
            return None
        out[name] = (float(value), counted)
    return out


def outputs_agree(
    worker: dict[str, tuple[float, int]],
    verifier: dict[str, tuple[float, int]],
    tol: dict[str, float],
) -> bool:
    names = set(tol)
    if set(worker) != names or set(verifier) != names:
        return False
    for name in names:
        wv, wn = worker[name]
        vv, vn = verifier[name]
        if wn != vn or not close(wv, vv, tol[name]):
            return False
    return True


def parse_result(
    path: Path, n: str, declared: dict[str, float], corpus_sha: str
) -> dict:
    """Load and type-check RESULT.json. Raises Fail on schema errors."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Fail(f"TASK-{n}: RESULT.json is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise Fail(f"TASK-{n}: RESULT.json top level must be an object")

    forbidden = [f for f in FORBIDDEN_RESULT_FIELDS if f in data]
    if forbidden:
        raise Fail(
            f"TASK-{n}: RESULT.json must not include {', '.join(forbidden)} "
            f"(dollar budget is gone; val_iterations is deferred)"
        )
    extra = sorted(set(data) - RESULT_KEY_SET)
    missing = sorted(RESULT_KEY_SET - set(data))
    if extra or missing:
        bits: list[str] = []
        if extra:
            bits.append("unknown keys " + ", ".join(extra))
        if missing:
            bits.append("missing " + ", ".join(missing))
        raise Fail(
            f"TASK-{n}: RESULT.json keys must be exactly "
            f"{list(RESULT_KEYS)}; {'; '.join(bits)}"
        )

    want_task = f"TASK-{n}"
    if data["task"] != want_task:
        raise Fail(
            f"TASK-{n}: RESULT.json task must be {want_task!r}, got {data['task']!r}"
        )

    subtype = data["subtype"]
    if subtype not in SUBTYPES:
        raise Fail(
            f"TASK-{n}: RESULT.json subtype must be one of "
            f"{sorted(SUBTYPES)}, got {subtype!r}"
        )

    verdict = data["verdict"]
    if subtype == "success":
        if verdict not in VERDICTS:
            raise Fail(
                f"TASK-{n}: RESULT.json verdict must be one of "
                f"{sorted(VERDICTS)} when subtype is success, got {verdict!r}"
            )
    elif verdict is not None:
        raise Fail(
            f"TASK-{n}: RESULT.json verdict must be null unless subtype is "
            f"success, got {verdict!r}"
        )

    hyp = data["hypothesis"]
    if not isinstance(hyp, str) or not hyp.strip() or "\n" in hyp:
        raise Fail(
            f"TASK-{n}: RESULT.json hypothesis must be one non-empty sentence"
        )
    why = data["why"]
    if not isinstance(why, str) or not why.strip() or "\n" in why:
        raise Fail(f"TASK-{n}: RESULT.json why must be one non-empty sentence")
    if re.search(r"\d", why) is None:
        raise Fail(f"TASK-{n}: RESULT.json why must contain a number")

    numbers = data["numbers"]
    if not isinstance(numbers, dict):
        raise Fail(f"TASK-{n}: RESULT.json numbers must be an object")
    extra_n = sorted(set(numbers) - set(declared))
    missing_n = sorted(set(declared) - set(numbers))
    if extra_n or missing_n:
        bits = []
        if extra_n:
            bits.append("not in the numbers block: " + ", ".join(extra_n))
        if missing_n:
            bits.append("declared but absent: " + ", ".join(missing_n))
        raise Fail(f"TASK-{n}: RESULT.json numbers " + "; ".join(bits))
    for name, entry in numbers.items():
        if not isinstance(entry, dict) or set(entry) != RESULT_NUMBER_KEYS:
            got = (
                sorted(entry) if isinstance(entry, dict) else type(entry).__name__
            )
            raise Fail(
                f"TASK-{n}: RESULT.json numbers.{name} keys must be exactly "
                f"{sorted(RESULT_NUMBER_KEYS)}, got {got}"
            )
        if not is_finite_number(entry["value"]):
            raise Fail(
                f"TASK-{n}: RESULT.json numbers.{name}.value must be a number"
            )
        if not isinstance(entry["within_tol"], bool):
            raise Fail(
                f"TASK-{n}: RESULT.json numbers.{name}.within_tol must be a boolean"
            )

    if not is_nonneg_int(data["turns_used"]):
        raise Fail(
            f"TASK-{n}: RESULT.json turns_used must be a non-negative integer"
        )
    if data["turn_cap"] != MAX_ATTEMPTS:
        raise Fail(
            f"TASK-{n}: RESULT.json turn_cap must be {MAX_ATTEMPTS}, "
            f"got {data['turn_cap']!r}"
        )

    sha = data["corpus_sha"]
    if not isinstance(sha, str) or CORPUS_SHA_VALUE.fullmatch(sha) is None:
        raise Fail(
            f"TASK-{n}: RESULT.json corpus_sha is not a 64-char lowercase hex "
            f"sha256: {sha!r}"
        )
    if sha != corpus_sha:
        raise Fail(
            f"TASK-{n}: RESULT.json corpus_sha is {sha}, README pin is {corpus_sha}"
        )

    forked = data["forked_from"]
    if forked is not None and (
        not isinstance(forked, str) or not forked.strip()
    ):
        raise Fail(
            f"TASK-{n}: RESULT.json forked_from must be null or a string"
        )
    if forked is not None and FORKED_FROM_RE.fullmatch(forked) is None:
        raise Fail(
            f"TASK-{n}: RESULT.json forked_from must be null or TASK-N / "
            f"TASK-N-b / TASK-N-c, got {forked!r}"
        )
    if not is_nonneg_int(data["fork_depth"]):
        raise Fail(
            f"TASK-{n}: RESULT.json fork_depth must be a non-negative integer"
        )
    if data["fork_depth"] > MAX_FORK_DEPTH:
        raise Fail(
            f"TASK-{n}: RESULT.json fork_depth is {data['fork_depth']} "
            f"(cap is {MAX_FORK_DEPTH}); a third fork is blocked, not TASK-N-d"
        )
    if forked is None and data["fork_depth"] != 0:
        raise Fail(
            f"TASK-{n}: RESULT.json fork_depth must be 0 when forked_from is null"
        )
    if forked is not None and data["fork_depth"] < 1:
        raise Fail(
            f"TASK-{n}: RESULT.json fork_depth must be >= 1 when forked_from "
            f"is set"
        )
    return data


def parse_launches(path: Path, n: str) -> list[dict]:
    """Load ``launches.json``. Raises Fail on schema errors."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Fail(f"TASK-{n}: launches.json is not valid JSON: {e}")
    if not isinstance(data, list):
        raise Fail(f"TASK-{n}: launches.json top level must be a list")
    out: list[dict] = []
    seen: set[str] = set()
    for i, rec in enumerate(data):
        loc = f"launches.json[{i}]"
        if not isinstance(rec, dict):
            raise Fail(f"TASK-{n}: {loc} must be an object")
        extra = sorted(set(rec) - LAUNCH_RECORD_KEY_SET)
        missing = sorted(LAUNCH_RECORD_KEY_SET - set(rec))
        if extra or missing:
            bits: list[str] = []
            if extra:
                bits.append("unknown keys " + ", ".join(extra))
            if missing:
                bits.append("missing " + ", ".join(missing))
            raise Fail(
                f"TASK-{n}: {loc} keys must be exactly "
                f"{list(LAUNCH_RECORD_KEYS)}; {'; '.join(bits)}"
            )
        lid = rec["id"]
        if not isinstance(lid, str) or not lid.strip():
            raise Fail(f"TASK-{n}: {loc}.id must be a non-empty string")
        if lid in seen:
            raise Fail(f"TASK-{n}: launches.json duplicate id {lid!r}")
        seen.add(lid)
        role = rec["role"]
        if role not in LAUNCH_ROLES:
            raise Fail(
                f"TASK-{n}: {loc}.role must be one of "
                f"{', '.join(sorted(LAUNCH_ROLES))}, got {role!r}"
            )
        at = rec["at"]
        if not isinstance(at, str) or not at.strip():
            raise Fail(f"TASK-{n}: {loc}.at must be a non-empty string")
        out.append(rec)
    return out


def family_launch_total(root: Path, n: str, fail: list[str]) -> int | None:
    """Sum ledger lengths for the fork family. None if a ledger is malformed."""
    total = 0
    for member in family_member_ids(n):
        path = root / "tasks" / f"TASK-{member}" / LAUNCHES
        if not path.is_file():
            continue
        try:
            total += len(parse_launches(path, member))
        except Fail as e:
            fail.append(str(e))
            return None
    return total


def check_launch_budget(
    root: Path, n: str, data: dict, fail: list[str]
) -> None:
    """RESULT.turns_used equals this task's ledger; family total vs cap 16."""
    path = root / "tasks" / f"TASK-{n}" / LAUNCHES
    if not path.is_file():
        fail.append(
            f"TASK-{n}: launches.json is missing; the coordinator or auditor "
            f"appends the ledger and RESULT.turns_used must equal its length"
        )
        return
    try:
        records = parse_launches(path, n)
    except Fail as e:
        fail.append(str(e))
        return
    used = data["turns_used"]
    if used != len(records):
        fail.append(
            f"TASK-{n}: RESULT.json turns_used is {used} but launches.json "
            f"has {len(records)} records"
        )
    total = family_launch_total(root, n, fail)
    if total is None:
        return
    print(
        f"  TASK-{n}: launches {len(records)}, family {total} "
        f"(cap {LAUNCH_BUDGET})"
    )
    subtype = data["subtype"]
    root_id = family_member_ids(n)[0]
    if subtype == "out_of_budget" and total < LAUNCH_BUDGET:
        fail.append(
            f"TASK-{n}: RESULT.json subtype is out_of_budget but family "
            f"TASK-{root_id} launches are {total} (cap is {LAUNCH_BUDGET})"
        )
    if subtype not in BUDGET_STOP_SUBTYPES and total > LAUNCH_BUDGET:
        own_over = len(records) > LAUNCH_BUDGET
        leaf = not has_letter_child_brief(root, n)
        if own_over or leaf:
            fail.append(
                f"TASK-{n}: RESULT.json subtype is {subtype} but family "
                f"TASK-{root_id} launches are {total} (cap is {LAUNCH_BUDGET})"
            )


def check_round_result(
    root: Path,
    n: str,
    brief: Brief,
    task_dir: Path,
    corpus_sha: str,
    base: str | None,
    head: str | None,
    fail: list[str],
) -> None:
    """Validate RESULT.json when present; require it for newly stopped tasks."""
    path = task_dir / RESULT
    rel = f"tasks/TASK-{n}/{RESULT}"
    status = brief.status

    if not path.is_file():
        if newly_stopped(root, n, base, head, status):
            fail.append(
                f"TASK-{n}: status is {status} after this PR but {rel} is "
                f"missing; the auditor writes RESULT at stop"
            )
        return

    try:
        data = parse_result(path, n, brief.tol, corpus_sha)
    except Fail as e:
        fail.append(str(e))
        return

    if status not in TERMINAL_STATUS:
        fail.append(
            f"TASK-{n}: {RESULT} is present but status is {status}; "
            f"the auditor writes RESULT at stop"
        )
        return

    subtype = data["subtype"]
    print(
        f"  TASK-{n} [{status}]: {RESULT} subtype={subtype} "
        f"verdict={data['verdict']!r}"
    )

    worker_p = task_dir / WORKER
    verifier_p = task_dir / VERIFIER
    worker = load_output_pairs(worker_p) if worker_p.is_file() else None
    verifier = load_output_pairs(verifier_p) if verifier_p.is_file() else None
    stale = stale_closed(status, brief.corpus_sha, corpus_sha)
    agreed = (
        worker is not None
        and verifier is not None
        and outputs_agree(worker, verifier, brief.tol)
    )

    if subtype == "success":
        if status != "closed" or stale:
            extra = "; STALE" if stale else ""
            fail.append(
                f"TASK-{n}: RESULT.json subtype is success but status is "
                f"{status}{extra} (success requires a live closed brief)"
            )
        if not worker_p.is_file() or worker is None:
            fail.append(
                f"TASK-{n}: RESULT.json subtype is success but {WORKER} is missing"
            )
        if not verifier_p.is_file() or verifier is None:
            fail.append(
                f"TASK-{n}: RESULT.json subtype is success but {VERIFIER} is missing"
            )
        if worker is not None and verifier is not None and not agreed:
            fail.append(
                f"TASK-{n}: RESULT.json subtype is success but {WORKER} and "
                f"{VERIFIER} do not agree within tol"
            )
        for name, entry in data["numbers"].items():
            if entry["within_tol"] is not True:
                fail.append(
                    f"TASK-{n}: RESULT.json subtype is success but "
                    f"numbers.{name}.within_tol is false"
                )
            claimed = float(entry["value"])
            t = brief.tol[name]
            if worker is not None and name in worker:
                if not close(claimed, worker[name][0], t):
                    fail.append(
                        f"TASK-{n}: RESULT.json numbers.{name}.value "
                        f"{num(claimed)} is not within tol of {WORKER} "
                        f"{num(worker[name][0])}"
                    )
            if verifier is not None and name in verifier:
                if not close(claimed, verifier[name][0], t):
                    fail.append(
                        f"TASK-{n}: RESULT.json numbers.{name}.value "
                        f"{num(claimed)} is not within tol of {VERIFIER} "
                        f"{num(verifier[name][0])}"
                    )

    if subtype == "out_of_turns" and head:
        try:
            got = max_output_rewrites(root, head, n, status)
        except Fail as e:
            fail.append(str(e))
        else:
            if got < MAX_ATTEMPTS:
                fail.append(
                    f"TASK-{n}: RESULT.json subtype is out_of_turns but rewrite "
                    f"count is {got} (cap is {MAX_ATTEMPTS})"
                )
    # out_of_turns without --head-ref: rewrite count is not decidable, same
    # as the existing edit-count gate.

    check_launch_budget(root, n, data, fail)

    if subtype == "stale" and not stale:
        fail.append(
            f"TASK-{n}: RESULT.json subtype is stale but the close stamp "
            f"matches the README pin"
        )

    if subtype == "blocked" and status != "blocked":
        fail.append(
            f"TASK-{n}: RESULT.json subtype is blocked but status is {status}"
        )
    # infra_failure: allowed subtype; evidence is not git-derivable.

    check_result_fork_fields(root, n, data, fail)


def check_result_fork_fields(
    root: Path, n: str, data: dict, fail: list[str]
) -> None:
    """RESULT fork fields must match the brief's letter suffix."""
    fid = parse_fork_id(n)
    if fid is None:
        return
    if fid.letter is not None and fid.letter not in FORK_DEPTH:
        fail.append(fork_depth_exceeded_message(n, fid))
        return
    if fid.depth == 0:
        if data["forked_from"] is not None or data["fork_depth"] != 0:
            fail.append(
                f"TASK-{n}: RESULT.json forked_from must be null and "
                f"fork_depth 0 on a root task"
            )
        return
    want_from = f"TASK-{fid.parent}"
    if data["forked_from"] != want_from:
        fail.append(
            f"TASK-{n}: RESULT.json forked_from must be {want_from!r}, "
            f"got {data['forked_from']!r}"
        )
    if data["fork_depth"] != fid.depth:
        fail.append(
            f"TASK-{n}: RESULT.json fork_depth must be {fid.depth}, "
            f"got {data['fork_depth']}"
        )
    parent_PATH = root / "tasks" / f"TASK-{fid.parent}" / RESULT
    if not parent_PATH.is_file():
        return
    try:
        parent = json.loads(parent_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(parent, dict):
        return
    pdepth = parent.get("fork_depth")
    if not is_nonneg_int(pdepth):
        return
    if data["fork_depth"] != pdepth + 1:
        fail.append(
            f"TASK-{n}: RESULT.json fork_depth must be parent "
            f"TASK-{fid.parent} depth {pdepth} + 1, got {data['fork_depth']}"
        )


def fork_depth_exceeded_message(n: str, fid: ForkId) -> str:
    return (
        f"TASK-{n}: fork suffix -{fid.letter} is not allowed "
        f"(depth 1 = -b, depth 2 = -c); a third fork must be blocked, "
        f"not open TASK-{fid.root}-d"
    )


def fork_trigger_ok(subtype: object, verdict: object) -> bool:
    if subtype == FORK_TRIGGER_SUBTYPE:
        return True
    return subtype == "success" and verdict == FORK_TRIGGER_VERDICT


def load_result_object(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def check_fence_identity(
    child_n: str, parent_n: str, child_text: str, parent_text: str, fail: list[str]
) -> None:
    """Byte-identical numbers/n/frame/identities vs the immediate parent."""
    for kind in FORK_FENCES:
        got = fence_interior(child_text, kind)
        want = fence_interior(parent_text, kind)
        if got == want:
            continue
        if kind in {"numbers", "n"}:
            boundary = (
                "same numbers+tolerances is a fork, changing them is a new task"
            )
        else:
            boundary = (
                f"changing ```{kind} redefines the measured set; that is a "
                f"new task, not a fork"
            )
        if got is None:
            fail.append(
                f"TASK-{child_n}: ```{kind} fence is missing; parent "
                f"TASK-{parent_n} has one; {boundary}"
            )
        elif want is None:
            fail.append(
                f"TASK-{child_n}: ```{kind} fence is present; parent "
                f"TASK-{parent_n} has none; {boundary}"
            )
        else:
            fail.append(
                f"TASK-{child_n}: ```{kind} fence is not byte-identical to "
                f"parent TASK-{parent_n}; {boundary}"
            )


def check_prior_attempts(
    child_n: str, parent_n: str, child_text: str, parent: dict, fail: list[str]
) -> None:
    section = prior_attempts_section(child_text)
    if section is None:
        fail.append(
            f"TASK-{child_n}: brief has no '## Prior Attempts' section"
        )
        return
    parent_task = f"TASK-{parent_n}"
    if parent_task not in section:
        fail.append(
            f"TASK-{child_n}: Prior Attempts must name parent {parent_task}"
        )
    hyp = parent.get("hypothesis")
    if isinstance(hyp, str) and hyp.strip() and hyp.strip() not in section:
        fail.append(
            f"TASK-{child_n}: Prior Attempts must quote the parent hypothesis"
        )
    why = parent.get("why")
    if isinstance(why, str) and why.strip() and why.strip() not in section:
        fail.append(
            f"TASK-{child_n}: Prior Attempts must quote the parent why"
        )
    verdict = parent.get("verdict")
    subtype = parent.get("subtype")
    if verdict is not None:
        token = str(verdict)
        label = "verdict"
    else:
        token = str(subtype) if subtype is not None else ""
        label = "subtype"
    if token and token not in section:
        fail.append(
            f"TASK-{child_n}: Prior Attempts must record parent {label} {token}"
        )
    numbers = parent.get("numbers")
    found = False
    if isinstance(numbers, dict):
        for name, entry in numbers.items():
            if not isinstance(name, str):
                continue
            value = None
            if isinstance(entry, dict) and "value" in entry:
                value = entry["value"]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if name in section and num(float(value)) in section:
                found = True
                break
    if not found:
        fail.append(
            f"TASK-{child_n}: Prior Attempts must include a key number "
            f"from the parent RESULT"
        )


def check_parent_result_immutable(
    root: Path, parent_n: str, child_n: str, head: str | None, fail: list[str]
) -> None:
    """Parent RESULT must exist and must not change after the child brief is added."""
    rel = f"tasks/TASK-{parent_n}/{RESULT}"
    path = root / "tasks" / f"TASK-{parent_n}" / RESULT
    if not path.is_file():
        fail.append(
            f"TASK-{child_n}: parent {rel} is missing; parent RESULT.json "
            f"is never deleted"
        )
        return
    if not head:
        return
    child_rel = f"tasks/TASK-{child_n}.md"
    try:
        if not in_tree(root, head, rel):
            fail.append(
                f"TASK-{child_n}: parent {rel} is missing at {head}; "
                f"parent RESULT.json is never deleted"
            )
            return
        child_sha = first_added(root, head, child_rel)
    except Fail as e:
        fail.append(str(e))
        return
    if child_sha is None:
        return
    try:
        touches = commits_touching(root, head, rel)
    except Fail as e:
        fail.append(str(e))
        return
    for sha in touches:
        try:
            after = is_ancestor(root, child_sha, sha)
        except Fail as e:
            fail.append(str(e))
            return
        if after:
            fail.append(
                f"TASK-{child_n}: parent {rel} was edited or deleted after "
                f"the fork (commit {sha[:8]}); parent RESULT.json is immutable"
            )
            return


def check_fork(
    root: Path,
    n: str,
    md: Path,
    brief: Brief,
    head: str | None,
    fail: list[str],
) -> None:
    """Enforce sibling-brief identity. Runs even when the child has no outputs."""
    fid = parse_fork_id(n)
    if fid is None:
        return
    if fid.letter is not None and fid.letter not in FORK_DEPTH:
        fail.append(fork_depth_exceeded_message(n, fid))
        return
    if fid.depth > 0:
        check_fork_child(root, fid, md, head, fail)
        print(
            f"  TASK-{n} [{brief.status}]: fork of TASK-{fid.parent} "
            f"depth {fid.depth}"
        )
        return
    child = child_task_id(fid)
    if child is None:
        return
    child_md = root / "tasks" / f"TASK-{child}.md"
    if child_md.is_file() and brief.status == "open":
        fail.append(
            f"TASK-{n}: status is open while fork TASK-{child} exists; "
            f"the parent round stays closed or escalated"
        )


def check_fork_child(
    root: Path, fid: ForkId, md: Path, head: str | None, fail: list[str]
) -> None:
    parent_n = fid.parent
    assert parent_n is not None
    parent_md = root / "tasks" / f"TASK-{parent_n}.md"
    if not parent_md.is_file():
        fail.append(
            f"TASK-{fid.task}: parent tasks/TASK-{parent_n}.md is missing"
        )
        return
    try:
        parent_brief = parse_brief(parent_md)
    except Fail as e:
        fail.append(f"TASK-{fid.task}: parent TASK-{parent_n} {e}")
        return
    if parent_brief.status not in TERMINAL_STATUS:
        fail.append(
            f"TASK-{fid.task}: parent TASK-{parent_n} status is "
            f"{parent_brief.status}; the parent round stays closed or escalated"
        )
    child_text = md.read_text(encoding="utf-8")
    parent_text = parent_md.read_text(encoding="utf-8")
    check_fence_identity(fid.task, parent_n, child_text, parent_text, fail)

    parent_result_PATH = root / "tasks" / f"TASK-{parent_n}" / RESULT
    if not parent_result_PATH.is_file():
        fail.append(
            f"TASK-{fid.task}: parent TASK-{parent_n} has no RESULT.json; "
            f"a fork needs the parent's round outcome"
        )
        return
    parent = load_result_object(parent_result_PATH)
    if parent is None:
        fail.append(
            f"TASK-{fid.task}: parent TASK-{parent_n}/RESULT.json is not "
            f"valid JSON"
        )
        return
    if not fork_trigger_ok(parent.get("subtype"), parent.get("verdict")):
        fail.append(
            f"TASK-{fid.task}: parent TASK-{parent_n} is "
            f"{parent.get('subtype')}/{parent.get('verdict')}; a fork is "
            f"allowed only when verdict is {FORK_TRIGGER_VERDICT} or "
            f"subtype is {FORK_TRIGGER_SUBTYPE}"
        )
    check_prior_attempts(fid.task, parent_n, child_text, parent, fail)
    check_parent_result_immutable(root, parent_n, fid.task, head, fail)


# ---------------------------------------------------------------------- one task


def check_task(
    root: Path,
    md: Path,
    conn: sqlite3.Connection,
    seconds: float,
    base: str | None,
    head: str | None,
    fail: list[str],
    corpus_sha: str,
) -> None:
    n = md.stem.split("-", 1)[1]
    try:
        brief = parse_brief(md)
    except Fail as e:
        fail.append(str(e))
        return
    status, tol, n_decl, frame, stamp, identities = brief

    task_dir = root / "tasks" / f"TASK-{n}"
    check_fork(root, n, md, brief, head, fail)
    check_round_result(
        root, n, brief, task_dir, corpus_sha, base, head, fail
    )

    if status in SUSPEND_STATUS:
        print(
            f"  TASK-{n} [{status}]: {len(tol)} number(s) declared; "
            f"suspended (replay, agreement, and edit-count not run)"
        )
        return

    if stale_closed(status, stamp, corpus_sha):
        print(stale_closed_line(n, stamp, corpus_sha))
        return

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

    skipped_by: dict[str, set[str]] = {}
    for k, replayed in replayed_by.items():
        held, skipped = check_identities(
            n,
            k,
            identities,
            tol,
            replayed,
            routes.get(k, {}),
            frame,
            fail,
        )
        skipped_by[k] = set(skipped)
        if skipped:
            print(
                f"  TASK-{n} [{status}]: {k} skipped {len(skipped)} identities "
                f"(not all SQL-routed)"
            )
        for h in held:
            print(f"  TASK-{n} [{status}]: identity {h}")
    if WORKER in skipped_by and VERIFIER in skipped_by:
        for line in identity_unchecked_on_both_sides(
            n, status, identities, skipped_by[WORKER], skipped_by[VERIFIER], fail
        ):
            print(f"  TASK-{n} [{status}]: {line}")

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

    # Neither branch may have started from the other's answer (plan §2.7).
    if base and head:
        check_independence(root, n, base, head, fail)

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
    ap.add_argument("--corpus", default=CORPUS_PATH_DEFAULT)
    ap.add_argument("--base-ref", default=None)
    ap.add_argument("--head-ref", default=None)
    ap.add_argument("--task", default=None, metavar="N")
    ap.add_argument("--sql-seconds", type=float, default=60.0)
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()

    fail: list[str] = []

    # The corpus is the only input. Confirm it is the one the README names.
    corpus = root / args.corpus
    readme = root / PIN_FILE
    if not corpus.is_file():
        print(f"output_check: FAIL\n  {args.corpus} does not exist; no number can be replayed")
        return 1
    if not readme.is_file():
        print(f"output_check: FAIL\n  {PIN_FILE} does not exist; the corpus hash is recorded there")
        return 1
    want = README_SHA.search(readme.read_text(encoding="utf-8"))
    if not want:
        print(f"output_check: FAIL\n  {PIN_FILE} records no sha256 for the corpus")
        return 1
    h = hashlib.sha256()
    with corpus.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != want.group(1):
        print(
            f"output_check: FAIL\n  {args.corpus} is {h.hexdigest()}, "
            f"{PIN_FILE} says {want.group(1)}"
        )
        return 1
    print(f"output_check: corpus {h.hexdigest()[:16]}… matches {PIN_FILE}")

    if args.base_ref and args.head_ref:
        print(f"output_check: history from {args.base_ref}..{args.head_ref}; independence enforced")
    elif args.head_ref:
        print("output_check: no base ref; independence is enforced on the pull request")
    else:
        print("output_check: no refs given; attempts and independence are enforced in CI")

    briefs = discover_briefs(root)
    if args.task is None:
        fail.extend(orphan_output_messages(root, briefs))
    else:
        try:
            briefs = filter_briefs(briefs, args.task)
        except Fail as e:
            print(f"output_check: FAIL\n  {e}")
            return 1
        print(f"output_check: only TASK-{brief_task_id(briefs[0])}")
    if not briefs:
        if not fail:
            print("output_check: no tasks/TASK-*.md; nothing to check")
            return 0
        print(
            "output_check: no tasks/TASK-*.md; "
            "output files remain without a matching brief"
        )
    else:
        print(f"output_check: {len(briefs)} task brief(s)")

    # Plan §4.1: on a pull request, fully check only tasks this diff touches.
    # Untouched tasks (including an open iterating disagreement on main) get a
    # frozen summary and cannot fail this PR. No base ref (push to main) still
    # walks every task. --task already selected one brief; do not freeze it.
    touched: frozenset[str] | None = None
    if args.task is None and args.base_ref and args.head_ref:
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
                frozen_summary(root, md, want.group(1))
                continue
            check_task(
                root,
                md,
                conn,
                args.sql_seconds,
                args.base_ref,
                args.head_ref,
                fail,
                want.group(1),
            )
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
