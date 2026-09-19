#!/usr/bin/env python3
"""Double and permute invariants on every declared SQL route.

A number that agrees on the live corpus can still be a constant in disguise:
``SELECT 391 FROM videos`` and ``rate / 122208`` both replay. Copying every
row, or shuffling row order, has no expected answer to special-case.

This script is a step of the ``output-check`` *job*, run from the pull-request
workspace (HEAD). After A1, PR CI copies ``output_check.py`` from base into
``/tmp/gate``; that copy cannot see this file until the PR merges. Do not call
this module from ``/tmp/gate/output_check.py``.

Construction (never writes under ``data/``):

  double   copy the corpus to ``$RUNNER_TEMP`` (or a local tempfile); re-insert
           every ``videos`` / ``windows`` / ``syllables`` row with primary keys
           prefixed ``dup:`` and ``video_id`` / ``uid`` updated to match.
           ``syllables.char`` is also prefixed so a type-count cutoff
           (``rare_share_*``, ``n_char < 10``) stays homogeneous of degree 0.
  permute  copy; rebuild those three tables with ``INSERT ... ORDER BY random()``.

Invariants, by declared name, against the original-corpus replay (not the
values the agent wrote):

  n_*                         exactly double
  agree_*  rare_share_*       stay within the brief's original tolerance
  rate_*_pm  gap_*  did_*

Permute: every declared number matches the original-corpus replay (same tols).

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

TABLES = ("videos", "windows", "syllables")
DUP_PREFIX = "dup:"
# Primary keys plus the FKs the brief names. Snapshot-then-insert, so the
# INSERT does not re-read the rows it just wrote.
PREFIX_COLUMNS = {
    "videos": frozenset({"video_id"}),
    "windows": frozenset({"uid", "video_id"}),
    # syllables.char is namespaced too. An absolute n_char < 10 cutoff is
    # not degree-0 if duplicated tokens keep the same glyph: 515 types on
    # this corpus sit in 5–9 occurrences, so rare_share_* would move while
    # still agreeing on the live corpus. Prefixing char keeps the listed
    # rare_share_* invariance and still catches a hardcoded denominator.
    "syllables": frozenset({"syl_id", "uid", "video_id", "char"}),
}
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def ident(name: str) -> str:
    """A table or column name used in generated SQL. Reject anything else."""
    if re.fullmatch(_IDENT, name) is None:
        raise Fail(f"relations: identifier {name!r} is not a simple name")
    return name


def family(name: str) -> str:
    """``count`` (must 2×) or ``rate`` (must stay). Unclassified raises."""
    if name.startswith("n_"):
        return "count"
    if name.startswith("agree_"):
        return "rate"
    if name.startswith("rare_share_"):
        return "rate"
    if name.startswith("rate_") and name.endswith("_pm"):
        return "rate"
    if name.startswith("gap_"):
        return "rate"
    if name.startswith("did_"):
        return "rate"
    raise Fail(
        f"relations: {name} matches no double/permute family "
        f"(n_ / agree_ / rare_share_ / rate_*_pm / gap_ / did_)"
    )


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


def replay_values(
    label: str,
    routes: dict[str, tuple[str, object]],
    conn: sqlite3.Connection,
    seconds: float,
    fail: list[str],
) -> dict[str, float]:
    """Replay SQL and derived names. Does not look at written values."""
    got: dict[str, float] = {}
    pending: dict[str, str] = {}
    for name in sorted(routes):
        kind, target = routes[name]
        if kind == "derived":
            pending[name] = str(target)
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


def check_task(
    root: Path,
    md: Path,
    orig_conn: sqlite3.Connection,
    doubled: Path,
    permuted: Path,
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

    if status in output_check.SUSPEND_STATUS:
        print(
            f"  TASK-{n} [{status}]: skipped (suspended; double/permute not run)"
        )
        return
    if output_check.stale_closed(status, stamp, corpus_sha):
        print(output_check.stale_closed_line(n, stamp, corpus_sha))
        return

    task_dir = root / "tasks" / f"TASK-{n}"
    paths = {
        output_check.WORKER: task_dir / output_check.WORKER,
        output_check.VERIFIER: task_dir / output_check.VERIFIER,
    }
    present = {k: p for k, p in paths.items() if p.is_file()}
    if not present:
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
            orig = replay_values(f"{k}", routes, orig_conn, seconds, fail)
            doubled_v = replay_values(
                f"{k}:double", routes, dup_conn, seconds, fail
            )
            perm_v = replay_values(
                f"{k}:permute", routes, perm_conn, seconds, fail
            )
            d_ok = 0
            p_ok = 0
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
            print(
                f"  TASK-{n} [{status}]: {k} double {d_ok}/{len(routes)} "
                f"permute {p_ok}/{len(routes)}"
            )
            note = output_check.check_period_identity(
                n, k, tol, orig, frame, fail
            )
            if note:
                print(f"  TASK-{n} [{status}]: period identity {note}")
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
    ap.add_argument("--corpus", default="data/corpus_v2.sqlite")
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
    readme = root / "README.md"
    data_DIR = (root / "data").resolve()

    try:
        sha = confirm_corpus(corpus, readme)
    except Fail as e:
        print(f"relations: FAIL\n  {e}")
        return 1
    print(f"relations: corpus {sha[:16]}… matches README.md")
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
        print(f"relations: temp corpora under {tmpdir} (not data/)")
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
