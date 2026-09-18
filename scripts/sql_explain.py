#!/usr/bin/env python3
"""SQL EXPLAIN dry-run against fixtures/schema.sqlite (contract §19).

Discovers SQL strings and sqlite execute paths in the repo, then runs
``EXPLAIN`` on each statement against the schema-only fixture (zero rows).
Parse/prepare failures and execute paths whose SQL cannot be resolved
fail the process (non-zero exit).

Does not mutate ``fixtures/schema.sqlite``. Paths are relative / CLI / env.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_SCHEMA = Path("fixtures") / "schema.sqlite"
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".cache",
    "models",
    "pip-cache",
    "tests",  # anti-example SQL lives here and must not be EXPLAINed as prod
}
SKIP_FILE_NAMES = {
    "sql_explain.py",
    "git_commit_pytest_hook.py",
}
SQL_HEAD = re.compile(
    r"^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|DROP|EXPLAIN|PRAGMA|REPLACE|ALTER)\b",
    re.I,
)
EXECUTE_FUNCS = {
    "execute",
    "executemany",
    "executescript",
    "read_sql_query",
    "read_sql",
}
PASSTHROUGH_FUNCS = {"scalar"}  # first SQL arg after the connection
IDENT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)")
FROM_JOIN = re.compile(
    r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.I,
)


class SqlExplainError(Exception):
    """A statement failed EXPLAIN / prepare against the schema fixture."""


class UnexecutedQueryPathError(Exception):
    """An execute() path exists whose SQL could not be resolved and EXPLAINed."""


class SchemaEmptyError(Exception):
    """schema.sqlite (or a stand-in connection) is not schema-only / zero-row."""


@dataclass(frozen=True)
class QueryPath:
    path: str
    lineno: int
    kind: str  # execute | executemany | executescript | read_sql_query | scalar | literal
    sql: str | None
    note: str = ""


@dataclass
class ExplainReport:
    explained: list[tuple[QueryPath, str]] = field(default_factory=list)
    failures: list[tuple[QueryPath, str]] = field(default_factory=list)
    unresolved: list[QueryPath] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures and not self.unresolved


def repo_root_from(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "fixtures" / "schema.sqlite").is_file():
            return candidate
    return here


def looks_like_sql(text: str) -> bool:
    s = text.strip()
    if len(s) < 12:
        return False
    match = SQL_HEAD.match(s)
    if not match:
        return False
    if not _balanced_parens(s) or s.rstrip().endswith(("(", ",", "AND", "OR", "FROM")):
        return False
    kind = match.group(1).upper()
    if kind == "SELECT" and not re.search(r"\bFROM\b", s, re.I):
        if not re.match(r"SELECT\s+(\d+|COUNT\s*\()", s, re.I):
            return False
    if kind == "INSERT" and not re.search(r"\bINTO\b", s, re.I):
        return False
    if kind == "CREATE" and not re.search(
        r"\b(TABLE|INDEX|VIEW|TRIGGER)\b", s, re.I
    ):
        return False
    return True


def _balanced_parens(s: str) -> bool:
    depth = 0
    in_s: str | None = None
    escape = False
    for ch in s:
        if in_s:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == in_s:
                in_s = None
            continue
        if ch in ("'", '"'):
            in_s = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def split_sql_statements(script: str) -> list[str]:
    """Split a script on top-level semicolons (quote-aware)."""
    out: list[str] = []
    buf: list[str] = []
    in_s: str | None = None
    escape = False
    for ch in script:
        if in_s:
            buf.append(ch)
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == in_s:
                in_s = None
            continue
        if ch in ("'", '"'):
            in_s = ch
            buf.append(ch)
            continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def count_qmark_placeholders(sql: str) -> int:
    n = 0
    in_s: str | None = None
    escape = False
    for ch in sql:
        if in_s:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == in_s:
                in_s = None
            continue
        if ch in ("'", '"'):
            in_s = ch
        elif ch == "?":
            n += 1
    return n


class _SqlCollector(ast.NodeVisitor):
    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.env_stack: list[dict[str, str]] = [{}]
        self.paths: list[QueryPath] = []
        self.to_sql_tables: set[str] = set()
        self.func_params: list[set[str]] = [set()]

    def _env(self) -> dict[str, str]:
        return self.env_stack[-1]

    def _push(self) -> None:
        self.env_stack.append(dict(self.env_stack[-1]))
        self.func_params.append(set())

    def _pop(self) -> None:
        self.env_stack.pop()
        self.func_params.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._push()
        params = {a.arg for a in node.args.args + node.args.kwonlyargs}
        if node.args.vararg:
            params.add(node.args.vararg.arg)
        if node.args.kwarg:
            params.add(node.args.kwarg.arg)
        self.func_params[-1] = params
        self.generic_visit(node)
        self._pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        val = self._eval_str(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name) and val is not None:
                self._env()[target.id] = val
                if looks_like_sql(val):
                    self.paths.append(
                        QueryPath(self.relpath, target.lineno, "literal", val)
                    )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            val = self._eval_str(node.value)
            if isinstance(node.target, ast.Name) and val is not None:
                self._env()[node.target.id] = val
                if looks_like_sql(val):
                    self.paths.append(
                        QueryPath(self.relpath, node.lineno, "literal", val)
                    )
        self.generic_visit(node)

    def _eval_str(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                    continue
                if isinstance(value, ast.FormattedValue):
                    inner = self._eval_str(value.value)
                    if inner is None and isinstance(value.value, ast.Name):
                        inner = self._env().get(value.value.id)
                    if inner is not None:
                        stripped = inner.strip()
                        if looks_like_sql(stripped) and stripped.upper().startswith(
                            "SELECT"
                        ):
                            parts.append(f"({stripped})")
                        else:
                            parts.append(inner)
                    else:
                        parts.append("'__p__'")
                    continue
                return None
            return "".join(parts)
        if isinstance(node, ast.Name):
            return self._env().get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._eval_str(node.left)
            right = self._eval_str(node.right)
            if left is not None and right is not None:
                return left + right
        return None

    def visit_Call(self, node: ast.Call) -> None:
        name: str | None = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr

        if name == "to_sql" and node.args:
            table = self._eval_str(node.args[0])
            if table:
                self.to_sql_tables.add(table)

        if name in EXECUTE_FUNCS and node.args:
            sql = self._eval_str(node.args[0])
            arg0 = node.args[0]
            passthrough = (
                sql is None
                and isinstance(arg0, ast.Name)
                and arg0.id in self.func_params[-1]
            )
            if passthrough:
                self.paths.append(
                    QueryPath(
                        self.relpath,
                        node.lineno,
                        name,
                        None,
                        note="passthrough",
                    )
                )
            else:
                self.paths.append(QueryPath(self.relpath, node.lineno, name, sql))

        if name in PASSTHROUGH_FUNCS and len(node.args) >= 2:
            sql = self._eval_str(node.args[1])
            self.paths.append(QueryPath(self.relpath, node.lineno, "scalar", sql))

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and looks_like_sql(node.value):
            self.paths.append(
                QueryPath(self.relpath, node.lineno, "literal", node.value)
            )


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name in SKIP_FILE_NAMES:
            continue
        yield path


def collect_query_paths(source: str, relpath: str = "<memory>") -> tuple[list[QueryPath], set[str]]:
    tree = ast.parse(source)
    collector = _SqlCollector(relpath)
    collector.visit(tree)
    # Deduplicate identical (lineno, kind, sql) while keeping unresolved.
    seen: set[tuple[int, str, str | None]] = set()
    unique: list[QueryPath] = []
    for item in collector.paths:
        key = (item.lineno, item.kind, item.sql)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique, collector.to_sql_tables


def collect_repo_query_paths(root: Path) -> tuple[list[QueryPath], set[str]]:
    paths: list[QueryPath] = []
    tables: set[str] = set()
    for file in iter_python_files(root):
        rel = str(file.relative_to(root))
        text = file.read_text(encoding="utf-8")
        try:
            file_paths, file_tables = collect_query_paths(text, rel)
        except SyntaxError as exc:
            raise UnexecutedQueryPathError(f"cannot parse {rel}: {exc}") from exc
        paths.extend(file_paths)
        tables |= file_tables
    return paths, tables


def _corpus_tables(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    return {r[0] for r in rows} | {"sqlite_master", "sqlite_temp_master"}


def _infer_aux_columns(sql: str, table: str) -> list[str]:
    cols: set[str] = set()
    aliases = {table}
    for match in FROM_JOIN.finditer(sql):
        name, alias = match.group(1), match.group(2)
        if name == table and alias:
            aliases.add(alias)
    for match in IDENT.finditer(sql):
        head, col = match.group(1), match.group(2)
        if head in aliases:
            cols.add(col)
    return sorted(cols) or ["placeholder"]


def prepare_working_connection(
    schema_path: Path,
    aux_tables: Iterable[str] = (),
    statements: Sequence[str] = (),
) -> sqlite3.Connection:
    """In-memory copy of schema.sqlite plus empty aux (temp) tables.

    The on-disk fixture is opened read-only and never written.
    """
    uri = schema_path.resolve().as_uri() + "?mode=ro"
    src = sqlite3.connect(uri, uri=True)
    try:
        dst = sqlite3.connect(":memory:")
        src.backup(dst)
    finally:
        src.close()
    existing = _corpus_tables(dst)
    needed = {name for name in aux_tables if name and name not in existing}

    def _is_temp_name(name: str) -> bool:
        lower = name.lower()
        return lower.startswith("_tmp") or lower.startswith("tmp_")

    for sql in statements:
        for match in FROM_JOIN.finditer(sql):
            name = match.group(1)
            if name not in existing and _is_temp_name(name):
                needed.add(name)
    for table in sorted(needed):
        if table in existing:
            continue
        cols: list[str] = []
        for sql in statements:
            cols.extend(_infer_aux_columns(sql, table))
        col_sql = ", ".join(f'"{c}" TEXT' for c in dict.fromkeys(cols))
        dst.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_sql})')
        existing.add(table)
    return dst


def assert_schema_empty(con: sqlite3.Connection) -> None:
    """Fail unless every user table has zero rows (contract: schema-only)."""
    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    nonempty: list[str] = []
    for name in tables:
        n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        if n != 0:
            nonempty.append(f"{name}={n}")
    if nonempty:
        raise SchemaEmptyError(
            "schema fixture must have zero rows; found " + ", ".join(nonempty)
        )


def explain_sql(con: sqlite3.Connection, sql: str) -> str:
    """Run EXPLAIN on one statement. Raises SqlExplainError on parse/prepare failure."""
    stmt = sql.strip()
    if not stmt:
        raise SqlExplainError("empty SQL")
    if stmt.upper().startswith("EXPLAIN"):
        to_run = stmt
        bind_sql = stmt
    else:
        to_run = "EXPLAIN " + stmt
        bind_sql = stmt
    n_bind = count_qmark_placeholders(bind_sql)
    params: tuple[object, ...] = (None,) * n_bind
    try:
        cur = con.execute(to_run, params)
        rows = cur.fetchall()
    except sqlite3.Error as exc:
        msg = str(exc)
        # CREATE of a table that already exists on the schema fixture still parsed.
        if stmt.lstrip().upper().startswith("CREATE") and "already exists" in msg:
            return "create-already-exists"
        raise SqlExplainError(f"{exc}: {stmt[:200]!r}") from exc
    if not rows:
        raise SqlExplainError(f"EXPLAIN returned no plan: {stmt[:200]!r}")
    return f"ok:{len(rows)}-ops"


def statements_for_path(item: QueryPath) -> list[str]:
    if not item.sql:
        return []
    if item.kind == "executescript":
        return [s for s in split_sql_statements(item.sql) if looks_like_sql(s) or SQL_HEAD.match(s.strip())]
    if looks_like_sql(item.sql) or item.kind != "literal":
        return [item.sql]
    return []


def run_explain_report(
    root: Path,
    schema_path: Path,
    paths: list[QueryPath] | None = None,
    aux_tables: Iterable[str] = (),
) -> ExplainReport:
    if paths is None:
        paths, collected_aux = collect_repo_query_paths(root)
        aux_tables = set(aux_tables) | collected_aux
    else:
        collected_aux = set(aux_tables)

    statements: list[str] = []
    for item in paths:
        statements.extend(statements_for_path(item))

    report = ExplainReport()
    con = prepare_working_connection(schema_path, collected_aux, statements)
    try:
        assert_schema_empty(con)
        for item in paths:
            if item.note == "passthrough":
                # Helper like scalar(con, sql) / execute(sql) where sql is a parameter.
                # Call sites and SQL literals are EXPLAINed separately.
                continue
            if item.sql is None:
                if item.kind == "scalar":
                    continue
                report.unresolved.append(item)
                continue
            stmts = statements_for_path(item)
            if not stmts:
                continue
            for stmt in stmts:
                try:
                    detail = explain_sql(con, stmt)
                    report.explained.append((item, detail))
                except SqlExplainError as exc:
                    report.failures.append((item, str(exc)))
    finally:
        con.close()
    return report


def format_report(report: ExplainReport) -> str:
    lines: list[str] = []
    lines.append(
        f"explained={len(report.explained)} failures={len(report.failures)} "
        f"unresolved={len(report.unresolved)}"
    )
    for item, detail in report.explained:
        lines.append(
            f"OK  {item.path}:{item.lineno} [{item.kind}] {detail} "
            f"{(item.sql or '')[:80]!r}"
        )
    for item, err in report.failures:
        lines.append(f"FAIL {item.path}:{item.lineno} [{item.kind}] {err}")
    for item in report.unresolved:
        lines.append(
            f"UNEXECUTED {item.path}:{item.lineno} [{item.kind}] "
            f"execute path SQL not resolved"
        )
    return "\n".join(lines) + "\n"


def report_or_raise(report: ExplainReport) -> None:
    if report.failures:
        msgs = "; ".join(f"{p.path}:{p.lineno} {err}" for p, err in report.failures[:8])
        raise SqlExplainError(f"{len(report.failures)} SQL EXPLAIN failure(s): {msgs}")
    if report.unresolved:
        msgs = ", ".join(f"{p.path}:{p.lineno}" for p in report.unresolved[:8])
        raise UnexecutedQueryPathError(
            f"{len(report.unresolved)} never-executed / unresolved query path(s): {msgs}"
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repo root (default: cwd, or nearest tree with fixtures/schema.sqlite)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="schema-only sqlite (default: <root>/fixtures/schema.sqlite or $SCHEMA_SQLITE)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root_from(args.root)
    schema = args.schema
    if schema is None:
        env = os.environ.get("SCHEMA_SQLITE")
        schema = Path(env) if env else root / DEFAULT_SCHEMA
    if not schema.is_file():
        print(f"schema fixture missing: {schema}", file=sys.stderr)
        return 1
    try:
        report = run_explain_report(root, schema)
    except (SqlExplainError, UnexecutedQueryPathError, SchemaEmptyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    sys.stdout.write(format_report(report))
    try:
        report_or_raise(report)
    except (SqlExplainError, UnexecutedQueryPathError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
