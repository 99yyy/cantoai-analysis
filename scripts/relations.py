#!/usr/bin/env python3
"""Double, permute and exclude invariants on every declared SQL route.

A number that agrees on the live corpus can still be a constant in disguise:
``SELECT 391 FROM videos`` and ``rate / 122208`` both replay. Copying every
row, shuffling row order, or dropping the rows the brief says are not
published, has no expected answer to special-case.

This script is a step of the ``output-check`` *job*. On a pull request CI
runs the base branch's copy from ``/tmp/gate`` (the whole ``scripts/``
directory as the base has it), like every other gate: a pull request is never
judged by the relations it brings. It imports ``output_check.py`` from its
own directory, so the two always come from the same branch.

Nothing project-specific is written here. Table names, keys, the columns to
namespace, the unit table and the number families come from
``gate_config.json`` (read through ``output_check.GATE_CONFIG``); the
published set comes from each brief's ``frame`` fence.

Construction (never writes next to the corpus):

  double   copy the corpus to ``$RUNNER_TEMP`` (or a local tempfile); re-insert
           every row of every configured table with its key, its refs and its
           ``type_columns`` prefixed ``dup:``. Namespacing the type column
           keeps an absolute type-frequency cutoff homogeneous of degree 0.
  permute  copy; rebuild the configured tables with ``INSERT ... ORDER BY random()``.
  exclude  copy; apply every ``frame`` predicate ``<table>.<column> <sql>`` as
           ``DELETE ... WHERE NOT (column sql)``; then delete rows whose refs
           no longer resolve, until nothing changes. One excluded corpus per
           distinct predicate list.

Invariants, by declared name, against the original-corpus replay (not the
values the agent wrote):

  count family   exactly double under double; unchanged under permute/exclude
  rate family    within the brief's tolerance under all three

Exclude runs when the brief's ``frame`` declares ``published_expected``;
dropping that line to opt out is a bar (history-audit). A number that moves
when the unpublished rows disappear was computed over the wrong set. Two
agents that share that mistake agree with each other and replay, and nothing
else in the gate can see it.

A brief may declare, in a fenced ``outside_frame`` block, names whose
definition reads rows outside the frame on purpose (a type-frequency cutoff
over the full table). Those names are not compared under exclude, and neither
is a ``derived:`` name whose expression reaches one of them. Every listed name
must be in the numbers block, and the exemption is printed per side. Adding a
name to that block is a bar move (history-audit). Double and permute still
apply to every name.

Anchor: when ``frame`` declares ``published_expected``, the excluded corpus
must hold exactly that many rows of the unit table (``published_expected_tol``,
default 0). A frame that no longer matches the corpus is a stale frame, not
a smaller published set. The anchor is checked as soon as the brief exists,
before either output does, so a wrong count fails on the brief's own pull
request instead of after two agents have been launched on it.

Score routes (``score:<metric>:<file>.jsonl``) do not read the corpus: they
are scored from prediction files, so their value is the same on every copy.
They are replayed here too, once, with output-check's scorer, and enter every
relation as that constant. A ``derived:`` name that mixes a score route with a
corpus number is therefore still checked -- ``1000 * n_count / 2 + 0 * rate_cer_pm``
cannot hide a hard-coded denominator. A side of which no number was compared
under double fails: a relation that checks nothing must not read as a pass.

An unclassified name is a failure. Suspended and STALE tasks are skipped, as
in output-check. Relations does not freeze on PR diff: a hardcoded denominator
in a closed task must still redden every run, including this repair PR.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import random
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("output_check", _HERE / "output_check.py")
assert _SPEC is not None and _SPEC.loader is not None
output_check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(output_check)

Fail = output_check.Fail

CONFIG = output_check.GATE_CONFIG
# Tables double/permute rewrite, in config order (parents before children).
TABLES = tuple(CONFIG["tables"])
UNIT_TABLE = str(CONFIG["unit_table"])
DUP_PREFIX = "dup:"
# Columns namespaced under double: each table's key, every column that refers
# to another table's key, and the declared ``type_columns`` (a categorical
# column that a type-frequency cutoff counts over: duplicated tokens must not
# keep the same type, or an absolute ``n < 10`` cutoff would move while still
# agreeing on the live corpus). Snapshot-then-insert, so the INSERT does not
# re-read the rows it just wrote.
PREFIX_COLUMNS = {
    t: frozenset(
        [spec["key"], *spec.get("refs", {}).keys(), *spec.get("type_columns", [])]
    )
    for t, spec in CONFIG["tables"].items()
}
FAMILIES = CONFIG["families"]
_KNOWN_FAMILIES = ("count", "rate")
for _fam in FAMILIES:
    if _fam not in _KNOWN_FAMILIES:
        raise Fail(
            f"relations: gate_config families has {_fam!r}; known: {', '.join(_KNOWN_FAMILIES)}"
        )
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def ident(name: str) -> str:
    """A table or column name used in generated SQL. Reject anything else."""
    if re.fullmatch(_IDENT, name) is None:
        raise Fail(f"relations: identifier {name!r} is not a simple name")
    return name


def family_rules() -> str:
    bits: list[str] = []
    for fam, rule in FAMILIES.items():
        pats = list(rule.get("prefix", [])) + [
            f"{p}*{sfx}" for p, sfx in rule.get("prefix_suffix", [])
        ]
        bits.append(f"{fam}: {' '.join(pats)}")
    return "; ".join(bits)


def family(name: str) -> str:
    """``count`` (must 2×) or ``rate`` (must stay), by the config's name
    prefixes. Unclassified raises."""
    for fam, rule in FAMILIES.items():
        for prefix in rule.get("prefix", []):
            if name.startswith(prefix):
                return fam
        for prefix, suffix in rule.get("prefix_suffix", []):
            if name.startswith(prefix) and name.endswith(suffix):
                return fam
    raise Fail(
        f"relations: {name} matches no double/permute family ({family_rules()})"
    )


OUTSIDE_FRAME_FENCE = output_check.DECLARATION_FENCES["outside_frame"]


def parse_outside_frame_block(label: str, text: str, declared: dict[str, float]) -> frozenset[str]:
    """Names whose definition reads rows outside the frame by declaration. One name per
    line, ``#`` comments allowed. The fence is optional; when present it must
    not be empty, must not repeat a name, and every name must be in the
    numbers block."""
    m = OUTSIDE_FRAME_FENCE.search(text)
    if not m:
        return frozenset()
    out: list[str] = []
    for raw in m.group(1).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if len(line.split()) != 1:
            raise Fail(f"{label}: outside_frame line is not one '<name>': {line!r}")
        if line in out:
            raise Fail(f"{label}: outside_frame lists {line} twice")
        if line not in declared:
            raise Fail(
                f"{label}: outside_frame names {line!r} which is not in the numbers block"
            )
        out.append(line)
    if not out:
        raise Fail(f"{label}: the outside_frame block is empty")
    return frozenset(out)


def outside_frame_closure(
    declared: frozenset[str], routes: dict[str, tuple[str, object]]
) -> frozenset[str]:
    """The declared names plus every ``derived:`` name whose expression reaches
    one of them (transitively). SQL routes are never added."""
    out = set(declared)
    changed = True
    while changed:
        changed = False
        for name, (kind, payload) in routes.items():
            if name in out or kind != "derived":
                continue
            try:
                names, _fields = output_check.parse_identity_expr(name, str(payload))
            except Fail:
                continue
            if names & out:
                out.add(name)
                changed = True
    return frozenset(out)


def column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    ident(table)
    rows = conn.execute(f"PRAGMA table_info({ident(table)})").fetchall()
    if not rows:
        raise Fail(f"relations: table {table} is missing")
    return [str(r[1]) for r in rows]


def temp_parent() -> str | None:
    """``RUNNER_TEMP`` when CI sets it; None means the process tempfile dir."""
    got = os.environ.get("RUNNER_TEMP")
    return got if got else None


def refuse_data_dir(path: Path, data_DIR: Path) -> None:
    """Temp corpora must not land under ``data/``."""
    resolved = path.resolve()
    data = data_DIR.resolve()
    try:
        resolved.relative_to(data)
    except ValueError:
        return
    raise Fail(f"relations: refusing to write a temp corpus under {data}")


def copy_corpus(src: Path, dest: Path, data_DIR: Path) -> None:
    refuse_data_dir(dest, data_DIR)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def double_corpus(src: Path, dest: Path, data_DIR: Path) -> None:
    """Re-insert every row of the three tables with ``dup:`` keys."""
    copy_corpus(src, dest, data_DIR)
    conn = sqlite3.connect(dest)
    try:
        for table in TABLES:
            cols = column_names(conn, table)
            prefix = PREFIX_COLUMNS[table]
            extra = sorted(c for c in prefix if c not in cols)
            if extra:
                raise Fail(
                    f"relations: {table} has no column {extra[0]} to prefix"
                )
            qtable = ident(table)
            qcols = ", ".join(ident(c) for c in cols)
            snap = ident("_snap_" + table)
            conn.execute(f"DROP TABLE IF EXISTS temp.{snap}")
            # Snapshot first: INSERT INTO t SELECT … FROM t would otherwise
            # see the rows it is writing.
            conn.execute(
                f"CREATE TEMP TABLE {snap} AS SELECT {qcols} FROM {qtable}"
            )
            exprs: list[str] = []
            for c in cols:
                qc = ident(c)
                if c in prefix:
                    exprs.append(f"'{DUP_PREFIX}' || {qc}")
                else:
                    exprs.append(qc)
            n_snap = conn.execute(
                f"SELECT COUNT(*) FROM {snap}"
            ).fetchone()[0]
            conn.execute(
                f"INSERT INTO {qtable} ({qcols}) "
                f"SELECT {', '.join(exprs)} FROM {snap}"
            )
            n_after = conn.execute(
                f"SELECT COUNT(*) FROM {qtable}"
            ).fetchone()[0]
            conn.execute(f"DROP TABLE {snap}")
            if n_after != 2 * n_snap:
                raise Fail(
                    f"relations: {table} has {n_after} rows after double; "
                    f"want 2 * {n_snap} = {2 * n_snap}"
                )
        conn.commit()
    finally:
        conn.close()


def permute_corpus(src: Path, dest: Path, data_DIR: Path) -> None:
    """Rebuild the three tables with ``INSERT ... ORDER BY random()``."""
    copy_corpus(src, dest, data_DIR)
    conn = sqlite3.connect(dest)
    try:
        order = list(TABLES)
        random.shuffle(order)
        for table in order:
            cols = column_names(conn, table)
            qtable = ident(table)
            qcols = ", ".join(ident(c) for c in cols)
            tmp = ident("_perm_" + table)
            conn.execute(f"DROP TABLE IF EXISTS temp.{tmp}")
            conn.execute(
                f"CREATE TEMP TABLE {tmp} AS "
                f"SELECT {qcols} FROM {qtable} ORDER BY random()"
            )
            conn.execute(f"DELETE FROM {qtable}")
            conn.execute(
                f"INSERT INTO {qtable} ({qcols}) "
                f"SELECT {qcols} FROM {tmp}"
            )
            conn.execute(f"DROP TABLE {tmp}")
        conn.commit()
    finally:
        conn.close()


PUBLISHED_EXPECTED = "published_expected"
PUBLISHED_EXPECTED_TOL = "published_expected_tol"

Predicate = tuple[str, str, str]


def exclude_corpus(
    src: Path, dest: Path, data_DIR: Path, predicates: list[Predicate]
) -> dict[str, int]:
    """Keep only the published set. Returns rows removed per table.

    Every ``frame`` predicate ``<table>.<column> <fragment>`` is applied as
    ``DELETE FROM table WHERE NOT (column fragment)`` (NULL counts as not
    published). Then rows whose ``refs`` no longer resolve are deleted, table
    by table, until nothing changes: a child of an excluded row is excluded.
    Tables without a predicate and without a dangling ref are untouched.
    """
    if not predicates:
        raise Fail("relations: exclude needs at least one frame predicate")
    copy_corpus(src, dest, data_DIR)
    conn = sqlite3.connect(dest)
    removed: dict[str, int] = {t: 0 for t in TABLES}
    try:
        for table, column, frag in predicates:
            if table not in CONFIG["tables"]:
                raise Fail(
                    f"relations: frame predicate names table {table!r}, which is "
                    f"not in gate_config tables"
                )
            if column not in column_names(conn, table):
                raise Fail(f"relations: {table} has no column {column} (frame predicate)")
            qt, qc = ident(table), ident(column)
            removed[table] += conn.execute(
                f"DELETE FROM {qt} WHERE COALESCE(({qt}.{qc} {frag}), 0) = 0"
            ).rowcount
        changed = True
        while changed:
            changed = False
            for table in TABLES:
                for col, parent in CONFIG["tables"][table].get("refs", {}).items():
                    if parent not in CONFIG["tables"]:
                        raise Fail(
                            f"relations: gate_config {table}.refs.{col} names unknown table {parent!r}"
                        )
                    pkey = CONFIG["tables"][parent]["key"]
                    qt, qc, qp, qk = ident(table), ident(col), ident(parent), ident(pkey)
                    n = conn.execute(
                        f"DELETE FROM {qt} WHERE NOT EXISTS "
                        f"(SELECT 1 FROM {qp} p WHERE p.{qk} = {qt}.{qc})"
                    ).rowcount
                    if n:
                        removed[table] += n
                        changed = True
        conn.commit()
        return removed
    finally:
        conn.close()


def published_units(conn: sqlite3.Connection) -> int:
    """Rows of the unit table that survive exclusion."""
    return int(conn.execute(f"SELECT COUNT(*) FROM {ident(UNIT_TABLE)}").fetchone()[0])


def removed_note(removed: dict[str, int]) -> str:
    return ", ".join(f"{n} {t}" for t, n in removed.items() if n)


def check_exclude_value(
    label: str, name: str, orig: float, got: float, tol: float, fail: list[str]
) -> bool:
    try:
        fam = family(name)
    except Fail as e:
        fail.append(str(e))
        return False
    t = 0.0 if fam == "count" else tol
    if not output_check.close(got, orig, t):
        fail.append(
            f"{label}:{name}: on the published set only {output_check.num(got)}, original "
            f"{output_check.num(orig)} (tol {t:g}) -- this number depends on rows "
            f"outside the frame"
        )
        return False
    return True


def check_published_anchor(
    n: str, frame: dict[str, float], exc_conn: sqlite3.Connection, fail: list[str]
) -> str | None:
    """``frame.published_expected`` must equal the published unit count."""
    if PUBLISHED_EXPECTED not in frame:
        return None
    want = frame[PUBLISHED_EXPECTED]
    tol = frame.get(PUBLISHED_EXPECTED_TOL, 0.0)
    got = published_units(exc_conn)
    if not output_check.close(float(got), want, tol):
        fail.append(
            f"TASK-{n}: frame.{PUBLISHED_EXPECTED} is {output_check.num(want)} but the "
            f"pinned corpus holds {got} published {UNIT_TABLE} rows (tol {tol:g})"
        )
        return None
    return f"frame.{PUBLISHED_EXPECTED} {output_check.num(want)} = published {UNIT_TABLE} rows"


def replay_values(
    label: str,
    routes: dict[str, tuple[str, object]],
    conn: sqlite3.Connection,
    seconds: float,
    fail: list[str],
    scores: "output_check.ScoreSet | None" = None,
) -> dict[str, float]:
    """Replay SQL, score and derived names. Does not look at written values."""
    got: dict[str, float] = {}
    pending: dict[str, str] = {}
    for name in sorted(routes):
        kind, target = routes[name]
        if kind == "derived":
            pending[name] = str(target)
            continue
        if kind == "score":
            # Corpus-independent: the same value on every copy of the corpus.
            if scores is None:
                fail.append(f"{label}:{name}: a score route needs an ```eval block")
                continue
            metric, pred = target  # type: ignore[misc]
            try:
                got[name] = scores.score(f"{label}:{name}", metric, pred)[0]
            except Fail as e:
                fail.append(str(e))
            continue
        try:
            got[name] = output_check.run_sql(
                conn, f"{label}:{name}", target, seconds
            )
        except Fail as e:
            fail.append(str(e))

    while pending:
        progressed = False
        for name in sorted(pending):
            try:
                v = output_check.eval_derived(
                    f"{label}:{name}", pending[name], got
                )
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
                    f"{label}:{name}: derived expression {pending[name]!r} "
                    f"cannot be resolved -- it names a number that is "
                    f"undeclared, that failed to replay, or that depends "
                    f"on this one"
                )
            break
    return got


def check_double_value(
    label: str, name: str, orig: float, got: float, tol: float, fail: list[str]
) -> bool:
    """Return True when the double invariant holds for ``name``."""
    try:
        fam = family(name)
    except Fail as e:
        fail.append(str(e))
        return False
    if fam == "count":
        want = 2.0 * orig
        if not output_check.close(got, want, 0.0):
            fail.append(
                f"{label}:{name}: double {output_check.num(got)}, want exactly "
                f"2 * {output_check.num(orig)} = {output_check.num(want)}"
            )
            return False
        return True
    if not output_check.close(got, orig, tol):
        fail.append(
            f"{label}:{name}: double {output_check.num(got)}, original "
            f"{output_check.num(orig)} (tol {tol:g})"
        )
        return False
    return True


def check_permute_value(
    label: str, name: str, orig: float, got: float, tol: float, fail: list[str]
) -> bool:
    try:
        fam = family(name)
    except Fail as e:
        fail.append(str(e))
        return False
    t = 0.0 if fam == "count" else tol
    if not output_check.close(got, orig, t):
        fail.append(
            f"{label}:{name}: permute {output_check.num(got)}, original "
            f"{output_check.num(orig)} (tol {t:g})"
        )
        return False
    return True


def side_routes(
    root: Path,
    n: str,
    path: Path,
    tol: dict[str, float],
    fail: list[str],
) -> dict[str, tuple[str, object]] | None:
    rows = output_check.parse_rows(path, tol, fail, n, root)
    if rows is None:
        return None
    routes: dict[str, tuple[str, object]] = {}
    for name in sorted(rows):
        try:
            routes[name] = output_check.route(
                path.name, n, name, str(rows[name]["query"]).strip(), root
            )
        except Fail as e:
            fail.append(str(e))
    if len(routes) != len(rows):
        return None
    return routes


class ExcludeCache:
    """One excluded corpus per distinct predicate list, built on first use."""

    def __init__(self, corpus: Path, tmpdir: Path, data_DIR: Path) -> None:
        self.corpus = corpus
        self.tmpdir = tmpdir
        self.data_DIR = data_DIR
        self.built: dict[tuple[Predicate, ...], Path] = {}

    def get(self, predicates: list[Predicate]) -> Path:
        key = tuple(predicates)
        if key not in self.built:
            dest = self.tmpdir / f"corpus_exclude_{len(self.built)}.sqlite"
            removed = exclude_corpus(self.corpus, dest, self.data_DIR, predicates)
            print(
                f"relations: exclude by {'; '.join(f'{t}.{c} {f}' for t, c, f in predicates)} "
                f"removed {removed_note(removed) or 'nothing'}"
            )
            self.built[key] = dest
        return self.built[key]


def check_task(
    root: Path,
    md: Path,
    orig_conn: sqlite3.Connection,
    doubled: Path,
    permuted: Path,
    excludes: ExcludeCache,
    seconds: float,
    fail: list[str],
    corpus_sha: str,
) -> None:
    n = md.stem.split("-", 1)[1]
    try:
        brief = output_check.parse_brief(md)
    except Fail as e:
        fail.append(str(e))
        return
    status, tol, _n_decl, frame, stamp, identities = brief
    try:
        text = md.read_text(encoding="utf-8")
        outside_frame = parse_outside_frame_block(md.name, text, tol)
        predicates = output_check.parse_frame_predicates(md.name, text)
        eval_set = output_check.parse_eval_block(md.name, text)
    except Fail as e:
        fail.append(str(e))
        return
    scores = (
        output_check.ScoreSet(root, eval_set, None) if eval_set is not None else None
    )

    if status in output_check.SUSPEND_STATUS:
        print(
            f"  TASK-{n} [{status}]: skipped (suspended; double/permute not run)"
        )
        return
    if output_check.stale_closed(status, stamp, corpus_sha):
        print(output_check.stale_closed_line(n, stamp, corpus_sha))
        return

    run_exclude = PUBLISHED_EXPECTED in frame
    exc_conn: sqlite3.Connection | None = None
    if run_exclude:
        if not predicates:
            fail.append(
                f"TASK-{n}: frame declares {PUBLISHED_EXPECTED} but no "
                f"<table>.<column> predicate line defines the published set"
            )
            return
        try:
            excluded = excludes.get(predicates)
        except Fail as e:
            fail.append(str(e))
            return
        exc_conn = sqlite3.connect(f"file:{excluded}?mode=ro", uri=True)
        anchor = check_published_anchor(n, frame, exc_conn, fail)
        if anchor:
            print(f"  TASK-{n} [{status}]: {anchor}")

    task_dir = root / "tasks" / f"TASK-{n}"
    paths = {
        output_check.WORKER: task_dir / output_check.WORKER,
        output_check.VERIFIER: task_dir / output_check.VERIFIER,
    }
    present = {k: p for k, p in paths.items() if p.is_file()}
    if not present:
        if exc_conn is not None:
            exc_conn.close()
        print(f"  TASK-{n} [{status}]: no output yet; double/permute not run")
        return

    dup_conn = sqlite3.connect(f"file:{doubled}?mode=ro", uri=True)
    perm_conn = sqlite3.connect(f"file:{permuted}?mode=ro", uri=True)
    try:
        for k, p in present.items():
            routes = side_routes(root, n, p, tol, fail)
            if routes is None:
                print(f"  TASK-{n} [{status}]: {k} is malformed")
                continue
            for name in routes:
                try:
                    family(name)
                except Fail as e:
                    fail.append(str(e))
            scored = sorted(nm for nm, (kind, _t) in routes.items() if kind == "score")
            if scored:
                print(
                    f"  TASK-{n} [{status}]: {k} {len(scored)} score route(s) replayed "
                    f"from predictions, constant on every copy: {', '.join(scored)}"
                )
            orig = replay_values(f"{k}", routes, orig_conn, seconds, fail, scores)
            doubled_v = replay_values(
                f"{k}:double", routes, dup_conn, seconds, fail, scores
            )
            perm_v = replay_values(
                f"{k}:permute", routes, perm_conn, seconds, fail, scores
            )
            exc_v: dict[str, float] = {}
            if exc_conn is not None:
                exc_v = replay_values(
                    f"{k}:exclude", routes, exc_conn, seconds, fail, scores
                )
            exempt = outside_frame_closure(outside_frame, routes) if run_exclude else frozenset()
            d_ok = 0
            p_ok = 0
            e_ok = 0
            for name in sorted(routes):
                if name not in orig:
                    continue
                t = tol[name]
                if name in doubled_v and check_double_value(
                    f"{k}", name, orig[name], doubled_v[name], t, fail
                ):
                    d_ok += 1
                if name in perm_v and check_permute_value(
                    f"{k}", name, orig[name], perm_v[name], t, fail
                ):
                    p_ok += 1
                if name in exempt:
                    continue
                if name in exc_v and check_exclude_value(
                    f"{k}", name, orig[name], exc_v[name], t, fail
                ):
                    e_ok += 1
            if not any(name in orig and name in doubled_v for name in routes):
                fail.append(
                    f"TASK-{n}: {k}: double compared none of {len(routes)} "
                    f"number(s); a relation that checks nothing is not a pass"
                )
            if run_exclude:
                exclude_note = f" exclude {e_ok}/{len(routes) - len(exempt)}"
                if exempt:
                    exclude_note += (
                        f" ({len(exempt)} outside_frame by declaration: "
                        f"{', '.join(sorted(exempt))})"
                    )
            else:
                exclude_note = f" exclude not run (frame has no {PUBLISHED_EXPECTED})"
            print(
                f"  TASK-{n} [{status}]: {k} double {d_ok}/{len(routes)} "
                f"permute {p_ok}/{len(routes)}{exclude_note}"
            )
            held, skipped = output_check.check_identities(
                n, k, identities, tol, orig, routes, frame, fail
            )
            if skipped:
                print(
                    f"  TASK-{n} [{status}]: {k} skipped {len(skipped)} identities "
                    f"(not all SQL-routed)"
                )
            for h in held:
                print(f"  TASK-{n} [{status}]: identity {h}")
    finally:
        dup_conn.close()
        perm_conn.close()
        if exc_conn is not None:
            exc_conn.close()


def confirm_corpus(corpus: Path, readme: Path) -> str:
    """Pin the input. A run that has not done this may not report a number."""
    if not corpus.is_file():
        raise Fail(f"{corpus.as_posix()} does not exist; no number can be replayed")
    if not readme.is_file():
        raise Fail("README.md does not exist; the corpus hash is recorded there")
    want = output_check.README_SHA.search(readme.read_text(encoding="utf-8"))
    if not want:
        raise Fail("README.md records no sha256 for the corpus")
    h = hashlib.sha256()
    with corpus.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    got = h.hexdigest()
    if got != want.group(1):
        print(got, want.group(1))
        raise Fail(
            f"{corpus.as_posix()} is {got}, README.md says {want.group(1)}"
        )
    return got


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--corpus", default=output_check.CORPUS_PATH_DEFAULT)
    ap.add_argument("--sql-seconds", type=float, default=60.0)
    ap.add_argument("--head-ref", default=None)
    ap.add_argument("--task", default=None, metavar="N")
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()
    corpus = (root / args.corpus).resolve() if not Path(args.corpus).is_absolute() else Path(args.corpus)
    # --corpus may be repo-relative (CI) or an absolute fixture path (tests).
    if not corpus.is_file():
        alt = Path(args.corpus).resolve()
        if alt.is_file():
            corpus = alt
    readme = root / output_check.PIN_FILE
    # Never write next to the corpus the gate reads.
    data_DIR = corpus.resolve().parent

    try:
        sha = confirm_corpus(corpus, readme)
    except Fail as e:
        print(f"relations: FAIL\n  {e}")
        return 1
    print(f"relations: corpus {sha[:16]}… matches {output_check.PIN_FILE}")
    if args.head_ref:
        print(f"relations: head {args.head_ref}; double/permute from this checkout")

    briefs = output_check.discover_briefs(root)
    if args.task is not None:
        try:
            briefs = output_check.filter_briefs(briefs, args.task)
        except Fail as e:
            print(f"relations: FAIL\n  {e}")
            return 1
        print(f"relations: only TASK-{output_check.brief_task_id(briefs[0])}")
    if not briefs:
        print("relations: no tasks/TASK-*.md; nothing to check")
        return 0

    parent = temp_parent()
    tmpdir = Path(
        tempfile.mkdtemp(prefix="relations-", dir=parent if parent else None)
    )
    fail: list[str] = []
    try:
        refuse_data_dir(tmpdir, data_DIR)
        doubled = tmpdir / "corpus_double.sqlite"
        permuted = tmpdir / "corpus_permute.sqlite"
        excludes = ExcludeCache(corpus, tmpdir, data_DIR)
        print(f"relations: temp corpora under {tmpdir} (not {data_DIR.name}/)")
        double_corpus(corpus, doubled, data_DIR)
        permute_corpus(corpus, permuted, data_DIR)

        orig_conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
        try:
            print(f"relations: {len(briefs)} task brief(s); no PR freeze")
            for md in briefs:
                check_task(
                    root,
                    md,
                    orig_conn,
                    doubled,
                    permuted,
                    excludes,
                    args.sql_seconds,
                    fail,
                    sha,
                )
        finally:
            orig_conn.close()
    except Fail as e:
        fail.append(str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if fail:
        print(f"relations: FAIL ({len(fail)})")
        for f in fail:
            print(f"  {f}")
        return 1
    print("relations: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
