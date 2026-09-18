#!/usr/bin/env python3
"""Process audit for cantoai-analysis (docs/AUDIT-SPEC.md).

Stdlib + sqlite3 only. Read-only: never mutates the corpus or analysis CSVs.

Each check is independent. Output is one line per check:

    PASS|FAIL|SKIP <id> <measured> (expected: …)

Non-zero exit if any FAIL. --round 2 adds R1–R5. --self-test uses temp
fixtures and exits 0 only if the runner itself behaves as specified.
"""
from __future__ import annotations

import argparse
import ast
import csv
import importlib.util
import inspect
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

CHECK_IDS_CORPUS = [
    "C1",
    "C2",
    "C3",
    "C4",
    "C5",
    "C6",
    "C7",
    "C8",
    "C9",
    "C13",
    "L1",
    "L2",
    "L3",
    "L4",
    "L5",
    "L6",
    "T1",
    "T3",
    "T4",
]
CHECK_IDS_ROUND2 = ["R1", "R2", "R3", "R4", "R5"]

SHEET_COLUMNS = [
    "window_id",
    "video_id",
    "film_flag",
    "clap_sing",
    "singing_prob",
    "var_db",
    "stratum",
    "human_label",
    "annotator_note",
    "forced_flag_sing",
]
HUMAN_LABELS = {
    "dialogue",
    "singing",
    "recitation",
    "mixed",
    "transcription_error",
    "unset",
}

SKIP_WALK_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".cache",
    "models",
    "pip-cache",
    "fixtures",  # never treat analysis fixtures as corpus when ICANTO_ROOT is monorepo root
}

# STATS.json nine integer counts (T4). Aliases cover likely pipeline key names.
STATS_COUNT_SPECS: list[tuple[str, str, tuple[str, ...]]] = [
    ("n_videos", "SELECT COUNT(*) FROM videos", ("n_videos", "videos", "num_videos", "video_count")),
    (
        "n_windows",
        "SELECT COUNT(*) FROM windows",
        ("n_windows", "windows", "num_windows", "window_count"),
    ),
    (
        "n_syllables",
        "SELECT COUNT(*) FROM syllables",
        ("n_syllables", "syllables", "num_syllables", "syllable_count"),
    ),
    (
        "n_windows_A",
        "SELECT COUNT(*) FROM windows WHERE tier='A'",
        ("n_windows_A", "n_tier_A_windows", "windows_A", "tier_A_windows", "n_A_windows"),
    ),
    (
        "n_windows_B",
        "SELECT COUNT(*) FROM windows WHERE tier='B'",
        ("n_windows_B", "n_tier_B_windows", "windows_B", "tier_B_windows", "n_B_windows"),
    ),
    (
        "n_windows_C",
        "SELECT COUNT(*) FROM windows WHERE tier='C'",
        ("n_windows_C", "n_tier_C_windows", "windows_C", "tier_C_windows", "n_C_windows"),
    ),
    (
        "n_syllables_A",
        "SELECT COUNT(*) FROM syllables WHERE tier='A'",
        ("n_syllables_A", "n_tier_A_syllables", "syllables_A", "tier_A_syllables"),
    ),
    (
        "n_syllables_B",
        "SELECT COUNT(*) FROM syllables WHERE tier='B'",
        ("n_syllables_B", "n_tier_B_syllables", "syllables_B", "tier_B_syllables"),
    ),
    (
        "n_syllables_C",
        "SELECT COUNT(*) FROM syllables WHERE tier='C'",
        ("n_syllables_C", "n_tier_C_syllables", "syllables_C", "tier_C_syllables"),
    ),
]

TIMESTAMP_COL_RE = re.compile(
    r"(start|end|dur|time|stamp|first_s|win_start)$", re.IGNORECASE
)
SHA_RE = re.compile(r"`([0-9a-f]{7,40})`")
HOURS_RE = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:h|hr|hours|小时)\b", re.IGNORECASE
)


@dataclass
class CheckResult:
    status: str  # PASS | FAIL | SKIP
    check_id: str
    measured: str
    expected: str

    def line(self) -> str:
        return f"{self.status} {self.check_id} {self.measured} (expected: {self.expected})"


@dataclass
class CorpusPaths:
    root: Path
    sqlite: Path | None
    stats: Path | None
    ids_txt: Path | None
    readmes: list[Path]
    common_py: Path | None
    export_09: Path | None
    validate_10: Path | None
    review_12: Path | None
    syllables_ab: Path | None
    info_jsons: list[Path]
    vad_files: list[Path]
    nested_dataset_v2: Path | None
    declared_dataset_dir: str | None


# ---------------------------------------------------------------------------
# filesystem / sqlite (read-only)
# ---------------------------------------------------------------------------


def env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser()


def analysis_root_from_env() -> Path:
    p = env_path("ANALYSIS_ROOT")
    if p is not None:
        return p.resolve()
    return Path(__file__).resolve().parents[1]



def _is_fixture_path(path: Path) -> bool:
    """True if path lives under a fixtures/ directory (analysis smoke trees)."""
    return "fixtures" in path.parts


def walk_files(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_WALK_DIRS and not d.endswith(".egg-info")
        ]
        # Audio dumps are huge and irrelevant to the audit.
        if Path(dirpath).name == "windows" and any(
            f.endswith((".flac", ".wav", ".mp3")) for f in filenames[:8]
        ):
            dirnames[:] = []
            continue
        for name in filenames:
            fp = Path(dirpath) / name
            if _is_fixture_path(fp):
                continue
            yield fp


def open_ro(sqlite_path: Path) -> sqlite3.Connection:
    uri = sqlite_path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def scalar(con: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> Any:
    row = con.execute(sql, args).fetchone()
    if row is None:
        return None
    return row[0]


def discover_corpus(root: Path) -> CorpusPaths:
    sqlite_candidates: list[Path] = []
    stats: Path | None = None
    ids_txt: Path | None = None
    readmes: list[Path] = []
    common_py: Path | None = None
    export_09: Path | None = None
    validate_10: Path | None = None
    review_12: Path | None = None
    syllables_ab: Path | None = None
    info_jsons: list[Path] = []
    vad_files: list[Path] = []
    nested: Path | None = None

    preferred_sqlite = [
        root / "corpus/dataset_v2/work/corpus.sqlite",
        root / "corpus/dataset_v2/dataset_v2/work/corpus.sqlite",
        root / "work/corpus.sqlite",
        root / "corpus.sqlite",
    ]
    preferred_common = [
        root / "corpus/dataset_v2/scripts/common.py",
        root / "scripts/common.py",
    ]
    preferred_stats = [
        root / "corpus/dataset_v2/dataset_v2/STATS.json",
        root / "corpus/dataset_v2/STATS.json",
        root / "STATS.json",
    ]
    for pref in preferred_common:
        if pref.is_file() and "def tier_of" in _read_text_head(pref, 200_000):
            common_py = pref
            break
    for pref in preferred_stats:
        if pref.is_file():
            stats = pref
            break

    for p in walk_files(root):
        if _is_fixture_path(p):
            continue
        name = p.name
        low = name.lower()
        if low == "corpus.sqlite":
            sqlite_candidates.append(p)
        elif low == "stats.json" and stats is None and not _is_fixture_path(p):
            stats = p
        elif low == "ids.txt" and ids_txt is None:
            ids_txt = p
        elif low in {"readme.md", "readme.txt"}:
            readmes.append(p)
        elif low == "syllables_ab.csv":
            syllables_ab = p
        elif name == "common.py" and common_py is None and not _is_fixture_path(p):
            if "def tier_of" in _read_text_head(p, 200_000):
                common_py = p
        elif re.match(r"09_.*\.py$", name) or (
            "09" in name and name.endswith(".py") and "export" in low
        ):
            export_09 = p
        elif re.match(r"10_validate.*\.py$", name) or name == "10_validate.py":
            validate_10 = p
        elif re.match(r"12_review_sample.*\.py$", name) or name == "12_review_sample.py":
            review_12 = p
        elif low == "info.json" or low.endswith(".info.json"):
            info_jsons.append(p)
        elif low.endswith((".json", ".csv", ".txt", ".log")) and (
            "vad" in low or "vad" in str(p.parent).lower()
        ):
            vad_files.append(p)

    sqlite: Path | None = None
    for pref in preferred_sqlite:
        if pref.is_file():
            sqlite = pref
            break
    if sqlite is None and sqlite_candidates:
        sqlite_candidates.sort(key=lambda p: (len(p.parts), str(p)))
        sqlite = sqlite_candidates[0]

    nested_a = root / "corpus/dataset_v2/dataset_v2"
    nested_b = root / "dataset_v2/dataset_v2"
    if nested_a.is_dir():
        nested = nested_a
    elif nested_b.is_dir():
        nested = nested_b

    if common_py is None:
        for p in walk_files(root):
            if p.suffix == ".py" and "def tier_of" in _read_text_head(p, 200_000):
                common_py = p
                break

    if export_09 is None:
        for p in walk_files(root):
            if p.suffix == ".py" and re.search(r"(^|/)0?9[_-]", str(p)):
                export_09 = p
                break

    declared = _declared_dataset_path(readmes)
    return CorpusPaths(
        root=root,
        sqlite=sqlite,
        stats=stats,
        ids_txt=ids_txt,
        readmes=readmes,
        common_py=common_py,
        export_09=export_09,
        validate_10=validate_10,
        review_12=review_12,
        syllables_ab=syllables_ab,
        info_jsons=info_jsons,
        vad_files=vad_files,
        nested_dataset_v2=nested,
        declared_dataset_dir=declared,
    )


def _read_text_head(path: Path, n: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.read(n)
    except OSError:
        return ""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _declared_dataset_path(readmes: list[Path]) -> str | None:
    for p in readmes:
        text = _read_text_head(p, 80_000)
        m = re.search(
            r"dataset_v2(?:/dataset_v2)?(?:/)?",
            text,
        )
        if m:
            # Prefer an explicit path-like mention.
            m2 = re.search(r"(?:at|in|路径|发布)[^\n]{0,40}(dataset_v2(?:/dataset_v2)?)", text)
            if m2:
                return m2.group(1)
            return m.group(0).rstrip("/")
    return None


def load_stats(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def flatten_json(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.update(flatten_json(v, key))
            out[str(k)] = v
    return out


# ---------------------------------------------------------------------------
# tier_of loading (C1 must actually call a recomputation)
# ---------------------------------------------------------------------------


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, "keys") and key in obj.keys():
        try:
            return obj[key]
        except Exception:
            pass
    if hasattr(obj, key):
        return getattr(obj, key)
    return default


def fallback_tier_of(window: Any) -> str:
    """Equivalent of the C7 rule + boiler/simp → B else A.

    Used only when corpus ``common.tier_of`` cannot be imported. C-rule matches
    AUDIT-SPEC C7; A vs B is the fixture convention (flag_boiler / flag_simp).
    """
    lang = _get_field(window, "lang")
    try:
        flag_sing = int(_get_field(window, "flag_sing") or 0)
    except (TypeError, ValueError):
        flag_sing = 0
    try:
        cps = float(_get_field(window, "chars_per_sec") or 0.0)
    except (TypeError, ValueError):
        cps = 0.0
    cov_raw = _get_field(window, "coverage")
    try:
        coverage = float(cov_raw) if cov_raw is not None else 1.0
    except (TypeError, ValueError):
        coverage = 1.0
    try:
        in_range = int(
            _get_field(window, "in_range")
            if _get_field(window, "in_range") is not None
            else 1
        )
    except (TypeError, ValueError):
        in_range = 1
    if lang != "yue" or flag_sing == 1 or cps > 8 or coverage < 0.2 or in_range == 0:
        return "C"
    try:
        boiler = int(_get_field(window, "flag_boiler") or 0)
    except (TypeError, ValueError):
        boiler = 0
    try:
        simp = int(_get_field(window, "flag_simp") or 0)
    except (TypeError, ValueError):
        simp = 0
    if boiler or simp:
        return "B"
    return "A"


def load_tier_of(common_py: Path | None) -> tuple[Callable[[Any], str], str]:
    if common_py is not None and common_py.is_file():
        fn = _import_tier_of(common_py)
        if fn is not None:
            return fn, f"imported:{common_py}"
        extracted = _extract_tier_of_from_source(common_py)
        if extracted is not None:
            return extracted, f"extracted:{common_py}"
    return fallback_tier_of, "fallback:C7+boiler/simp"


def _import_tier_of(path: Path) -> Callable[[Any], str] | None:
    mod_name = "_icanto_common_audit_" + re.sub(r"[^A-Za-z0-9_]", "_", str(path.resolve()))
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        return None
    fn = getattr(mod, "tier_of", None)
    return fn if callable(fn) else None


def _extract_tier_of_from_source(path: Path) -> Callable[[Any], str] | None:
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "tier_of":
            module = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(module)
            ns: dict[str, Any] = {}
            try:
                exec(compile(module, str(path), "exec"), ns, ns)
            except Exception:
                return None
            fn = ns.get("tier_of")
            return fn if callable(fn) else None
    return None


def call_tier_of(fn: Callable[[Any], str], row: dict[str, Any]) -> str:
    ns = SimpleNamespace(**row)
    attempts: list[Any] = [row, ns]
    try:
        sig = inspect.signature(fn)
        params = [
            p
            for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
        ]
        if len(params) == 1:
            attempts = [row, ns]
        else:
            kwargs = {p.name: row[p.name] for p in params if p.name in row}
            if kwargs:
                return str(fn(**kwargs))
    except (TypeError, ValueError):
        pass
    last_err: Exception | None = None
    for arg in attempts:
        try:
            return str(fn(arg))
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"tier_of failed: {last_err}")


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# result helpers
# ---------------------------------------------------------------------------


def _pass(cid: str, measured: str, expected: str) -> CheckResult:
    return CheckResult("PASS", cid, measured, expected)


def _fail(cid: str, measured: str, expected: str) -> CheckResult:
    return CheckResult("FAIL", cid, measured, expected)


def _skip(cid: str, measured: str, expected: str) -> CheckResult:
    return CheckResult("SKIP", cid, measured, expected)


def _run_check(cid: str, fn: Callable[[], CheckResult]) -> CheckResult:
    try:
        return fn()
    except Exception as exc:
        tb = traceback.format_exc(limit=2).replace("\n", " ")
        return _fail(cid, f"error={type(exc).__name__}:{exc}", f"check runs; {tb[:180]}")


# ---------------------------------------------------------------------------
# C checks
# ---------------------------------------------------------------------------


def check_c1(con: sqlite3.Connection, paths: CorpusPaths) -> CheckResult:
    fn, src = load_tier_of(paths.common_py)
    n = 0
    mismatches = 0
    examples: list[str] = []
    for row in con.execute("SELECT * FROM windows"):
        stored = row["tier"]
        recomputed = call_tier_of(fn, row_to_dict(row))
        n += 1
        if str(recomputed) != str(stored):
            mismatches += 1
            if len(examples) < 3:
                examples.append(f"{row['uid']}:{stored}->{recomputed}")
    measured = f"mismatches={mismatches}/{n} via={src}"
    if examples:
        measured += f" e.g. {','.join(examples)}"
    if mismatches == 0 and n > 0:
        return _pass("C1", measured, "== 0 (must recompute via tier_of)")
    if n == 0:
        return _fail("C1", measured, "== 0 (must recompute via tier_of)")
    return _fail("C1", measured, "== 0")


def check_c2(con: sqlite3.Connection) -> CheckResult:
    n = scalar(
        con,
        "SELECT COUNT(*) FROM syllables s JOIN windows w ON s.uid=w.uid "
        "WHERE s.tier IS NOT w.tier",
    )
    return (_pass if n == 0 else _fail)("C2", f"mismatch_rows={n}", "== 0")


def check_c3(con: sqlite3.Connection) -> CheckResult:
    n = scalar(
        con,
        "SELECT COUNT(*) FROM syllables WHERE tier IN ('A','B') AND "
        "(jp_realized IS NULL OR jp_realized='' OR jp_match='none')",
    )
    return (_pass if n == 0 else _fail)("C3", f"empty_or_none={n}", "== 0")


def check_c4(con: sqlite3.Connection) -> CheckResult:
    n = scalar(
        con,
        "SELECT COUNT(*) FROM syllables WHERE tier IN ('A','B') AND IFNULL(dur,0)<=0",
    )
    return (_pass if n == 0 else _fail)("C4", f"dur_le_0={n}", "== 0")


def check_c5(con: sqlite3.Connection) -> CheckResult:
    n = scalar(
        con,
        "SELECT COUNT(*) FROM windows WHERE tier IN ('A','B') AND coverage>1.2",
    )
    mx = scalar(
        con,
        "SELECT MAX(coverage) FROM windows",
    )
    n_gt1 = scalar(con, "SELECT COUNT(*) FROM windows WHERE coverage>1")
    measured = f"coverage_gt_1.2_AB={n} coverage_gt_1_all={n_gt1} max={mx}"
    return (_pass if n == 0 else _fail)("C5", measured, "== 0")


def check_c6(con: sqlite3.Connection) -> CheckResult:
    vals = [
        r[0]
        for r in con.execute(
            "SELECT aligned, COUNT(*) FROM windows GROUP BY aligned ORDER BY aligned"
        )
    ]
    nuniq = len(vals)
    n = scalar(con, "SELECT COUNT(*) FROM windows")
    measured = f"aligned_values={tuple(vals)} nuniq={nuniq} n={n}"
    return (_pass if nuniq > 1 else _fail)("C6", measured, "nuniq > 1")


def check_c7(con: sqlite3.Connection) -> CheckResult:
    unexplained = scalar(
        con,
        "SELECT COUNT(*) FROM windows WHERE tier='C' AND NOT ("
        "IFNULL(lang,'')!='yue' OR IFNULL(flag_sing,0)=1 OR IFNULL(chars_per_sec,0)>8 "
        "OR IFNULL(coverage,1)<0.2 OR IFNULL(in_range,1)=0)",
    )
    union_n = scalar(
        con,
        "SELECT COUNT(*) FROM windows WHERE IFNULL(lang,'')!='yue' "
        "OR IFNULL(flag_sing,0)=1 OR IFNULL(chars_per_sec,0)>8 "
        "OR IFNULL(coverage,1)<0.2 OR IFNULL(in_range,1)=0",
    )
    n_c = scalar(con, "SELECT COUNT(*) FROM windows WHERE tier='C'")
    # Full-corpus Sep-18 size is 472; otherwise require union == n_C (library-consistent).
    expected_union = 472 if n_c == 472 else n_c
    measured = f"unexplained={unexplained} union={union_n} n_C={n_c}"
    ok = unexplained == 0 and union_n == expected_union
    expected = f"unexplained==0 union=={expected_union}"
    return (_pass if ok else _fail)("C7", measured, expected)


def _extract_sql_assignment(src: str, names: tuple[str, ...]) -> str | None:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id in names:
                        if isinstance(node.value, ast.Constant) and isinstance(
                            node.value.value, str
                        ):
                            return node.value.value
            if isinstance(node, ast.FunctionDef) and node.name in names:
                for stmt in node.body:
                    if isinstance(stmt, ast.Return) and isinstance(
                        stmt.value, ast.Constant
                    ) and isinstance(stmt.value.value, str):
                        return stmt.value.value
    for name in names:
        m = re.search(
            rf"{re.escape(name)}\s*=\s*[rRfFuU]{{0,3}}(['\"]{{3}})(.*?)\1",
            src,
            re.S,
        )
        if m:
            return m.group(2)
    m = re.search(r"(SELECT\s+.+?)(?:\n\s*\"\"\"|\n\s*'''|$)", src, re.S | re.I)
    if m and "from" in m.group(1).lower():
        sql = m.group(1).strip()
        sql = sql.strip().strip('"').strip("'")
        if sql.upper().startswith("SELECT"):
            return sql
    return None


def check_c8(con: sqlite3.Connection, paths: CorpusPaths) -> CheckResult:
    n_runs = None
    if table_exists(con, "runs"):
        n_runs = scalar(con, "SELECT COUNT(*) FROM runs")
    sql = None
    if paths.export_09 and paths.export_09.is_file():
        sql = _extract_sql_assignment(
            _read_text(paths.export_09),
            ("EXPORT_SQL", "SYLLABLES_AB_SQL", "AB_SQL", "export_sql"),
        )
    if not sql:
        sql = (
            "SELECT s.syl_id, s.uid, s.video_id, s.pos, s.char, s.start, s.end, "
            "s.dur, s.tier, s.jp_default, s.jp_ctx, s.jp_realized, s.jp_match "
            "FROM syllables s JOIN windows w ON w.uid=s.uid "
            "WHERE w.tier IN ('A','B') ORDER BY s.syl_id"
        )
    if paths.syllables_ab is None or not paths.syllables_ab.is_file():
        return _skip(
            "C8",
            f"runs={n_runs} csv=missing sql_source="
            f"{paths.export_09.name if paths.export_09 else 'default'}",
            "diffs==0; print runs and diffs",
        )
    try:
        sql_rows = list(con.execute(sql))
    except sqlite3.Error as exc:
        return _fail("C8", f"runs={n_runs} sql_error={exc}", "diffs==0")

    with paths.syllables_ab.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        csv_fields = reader.fieldnames or []
        csv_rows = list(reader)

    sql_cols = [d[0] for d in con.execute(sql).description]
    by_id: dict[str, sqlite3.Row] = {}
    sql_has_id = "syl_id" in sql_cols
    if sql_has_id:
        for r in sql_rows:
            by_id[str(r["syl_id"])] = r

    diffs = 0
    compared = 0
    common_cols = [c for c in csv_fields if c in sql_cols]
    if not common_cols:
        diffs = max(len(sql_rows), len(csv_rows))
    elif sql_has_id and "syl_id" in csv_fields:
        csv_ids = {str(r.get("syl_id")) for r in csv_rows}
        sql_ids = set(by_id)
        diffs += len(csv_ids.symmetric_difference(sql_ids))
        for r in csv_rows:
            sid = str(r.get("syl_id"))
            if sid not in by_id:
                continue
            srow = by_id[sid]
            for col in common_cols:
                compared += 1
                if not _cell_equal(srow[col], r.get(col), col):
                    diffs += 1
    else:
        n = max(len(sql_rows), len(csv_rows))
        diffs += abs(len(sql_rows) - len(csv_rows))
        for i in range(min(len(sql_rows), len(csv_rows))):
            srow = sql_rows[i]
            crow = csv_rows[i]
            for col in common_cols:
                compared += 1
                if not _cell_equal(srow[col], crow.get(col), col):
                    diffs += 1
        _ = n

    measured = (
        f"runs={n_runs} diffs={diffs} compared_cells={compared} "
        f"sql_rows={len(sql_rows)} csv_rows={len(csv_rows)}"
    )
    # Tolerance policy: none. ±0.01 timestamp drift still counts as a diff (do not wash green).
    return (_pass if diffs == 0 else _fail)("C8", measured, "diffs==0 (no timestamp tolerance)")


def _cell_equal(sql_val: Any, csv_val: Any, col: str) -> bool:
    if sql_val is None and (csv_val is None or csv_val == ""):
        return True
    if sql_val is None or csv_val is None:
        return False
    sv = str(sql_val)
    cv = str(csv_val)
    if sv == cv:
        return True
    try:
        fv_s = float(sql_val)
        fv_c = float(csv_val)
    except (TypeError, ValueError):
        return False
    # Exact float equality after parse; 0.01 drift is a FAIL.
    if fv_s == fv_c:
        return True
    if TIMESTAMP_COL_RE.search(col):
        return False
    return False


def check_c9(paths: CorpusPaths) -> CheckResult:
    declared = paths.declared_dataset_dir or "unspecified"
    nested = paths.nested_dataset_v2
    nested_s = str(nested) if nested else "none"
    # Documented path must match the real published directory.
    declared_nested = "dataset_v2/dataset_v2" in declared.replace("\\", "/")
    actual_nested = nested is not None
    ok = declared_nested == actual_nested and not (
        actual_nested and not declared_nested
    )
    # Nested dir while README only says dataset_v2/ → FAIL (Sep-18).
    if actual_nested and not declared_nested:
        ok = False
    if not actual_nested and declared_nested:
        ok = False
    measured = f"readme_declares={declared} nested_dir={nested_s}"
    return (_pass if ok else _fail)(
        "C9", measured, "README path matches real dataset_v2 location"
    )


def check_c13(con: sqlite3.Connection, paths: CorpusPaths) -> CheckResult:
    n_pub = scalar(
        con, "SELECT COUNT(*) FROM syllables WHERE tier IN ('A','B')"
    )
    frame_sql = None
    reported = None
    src = "default:A+B AND dur>0"
    if paths.review_12 and paths.review_12.is_file():
        text = _read_text(paths.review_12)
        frame_sql = _extract_sql_assignment(
            text,
            ("FRAME_SQL", "SAMPLING_FRAME_SQL", "sampling_frame_sql"),
        )
        m = re.search(
            r"REPORTED_N\s*=\s*(\d+)|PUBLIC_PUBLISHED_N\s*=\s*(\d+)|"
            r"对外[^\n]{0,20}(\d{3,})",
            text,
        )
        if m:
            reported = int(next(g for g in m.groups() if g))
        src = paths.review_12.name
    if not frame_sql:
        frame_sql = (
            "SELECT COUNT(*) FROM syllables s JOIN windows w ON s.uid=w.uid "
            "WHERE w.tier IN ('A','B') AND IFNULL(s.dur,0)>0"
        )
    try:
        if frame_sql.strip().lower().startswith("select count"):
            n_frame = scalar(con, frame_sql)
        else:
            n_frame = scalar(con, f"SELECT COUNT(*) FROM ({frame_sql}) AS _frame")
    except sqlite3.Error:
        n_frame = scalar(
            con,
            "SELECT COUNT(*) FROM syllables WHERE tier IN ('A','B') AND IFNULL(dur,0)>0",
        )
        src = "fallback:dur>0"
    if reported is None:
        # External published-set size: A+B count (Sep-18: 164693).
        reported = n_pub
        for p in paths.readmes:
            m = re.search(
                r"(发布|published|A\+B)[^\n]{0,40}(\d{3,})",
                _read_text_head(p, 40_000),
                re.I,
            )
            if m:
                reported = int(m.group(2))
                break
        stats = load_stats(paths.stats)
        for k in ("n_published_syllables", "published_syllables", "n_AB_syllables"):
            if k in stats and isinstance(stats[k], (int, float)):
                reported = int(stats[k])
    cov = (n_frame / n_pub) if n_pub else None
    cov_s = f"{cov:.4f}" if cov is not None else "nan"
    measured = (
        f"frame={n_frame} published={n_pub} coverage={cov_s} "
        f"reported={reported} src={src}"
    )
    ok = reported == n_frame
    return (_pass if ok else _fail)(
        "C13",
        measured,
        "reported == sampling-frame size (not published-set size unless equal)",
    )


# ---------------------------------------------------------------------------
# L checks
# ---------------------------------------------------------------------------


def _channel_from_info(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for k in ("channel_id", "uploader_id", "channel", "uploader"):
        v = data.get(k)
        if v:
            return str(v)
    return None


def check_l1(paths: CorpusPaths) -> CheckResult:
    if not paths.info_jsons:
        return _skip("L1", "n_info=0 n_channels=missing", "n_channels!=1")
    channels: set[str] = set()
    n = 0
    for p in paths.info_jsons:
        n += 1
        ch = _channel_from_info(p)
        if ch:
            channels.add(ch)
    n_ch = len(channels)
    measured = f"n_info={n} n_channels={n_ch} channels={sorted(channels)[:5]}"
    if n_ch == 1:
        return _fail("L1", measured, "n_channels!=1")
    if n_ch == 0:
        return _fail("L1", measured, "n_channels!=1 (need channel_id)")
    return _pass("L1", measured, "n_channels!=1")


def check_l2(con: sqlite3.Connection) -> CheckResult:
    row = con.execute(
        "SELECT text_clean, COUNT(*) AS n FROM windows WHERE tier='A' "
        "AND text_clean IS NOT NULL AND text_clean!='' "
        "GROUP BY text_clean ORDER BY n DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return _pass("L2", "max_text_clean_in_A=0", "<= 2")
    n = int(row["n"])
    sample = str(row["text_clean"])[:40]
    return (_pass if n <= 2 else _fail)(
        "L2", f"max_text_clean_in_A={n} text={sample!r}", "<= 2"
    )


def check_l3(con: sqlite3.Connection) -> CheckResult:
    row = con.execute(
        "SELECT COUNT(*) AS n_groups, IFNULL(SUM(n),0) AS n_rows FROM ("
        "SELECT text_clean, COUNT(*) AS n FROM windows "
        "WHERE tier IN ('A','B') AND text_clean IS NOT NULL AND text_clean!='' "
        "GROUP BY text_clean HAVING COUNT(*)>1)"
    ).fetchone()
    n_groups = int(row["n_groups"] or 0)
    n_rows = int(row["n_rows"] or 0)
    measured = f"dup_groups={n_groups} dup_rows={n_rows}"
    return (_pass if n_groups == 0 else _fail)("L3", measured, "dup_groups==0")


def check_l4(con: sqlite3.Connection) -> CheckResult:
    overflow = 0
    max_exc = 0.0
    for row in con.execute(
        "SELECT s.syl_id, s.start AS ss, s.end AS se, w.start AS ws, w.end AS we "
        "FROM syllables s JOIN windows w ON s.uid=w.uid "
        "WHERE s.start IS NOT NULL AND s.end IS NOT NULL "
        "AND w.start IS NOT NULL AND w.end IS NOT NULL"
    ):
        ss, se, ws, we = (row["ss"], row["se"], row["ws"], row["we"])
        below = float(ws) - float(ss)
        above = float(se) - float(we)
        if below > 0 or above > 0:
            overflow += 1
            max_exc = max(max_exc, below, above)

    overlaps = 0
    prev: dict[str, float] = {}
    for row in con.execute(
        "SELECT video_id, uid, start, end FROM windows "
        "WHERE start IS NOT NULL AND end IS NOT NULL "
        "ORDER BY video_id, start, uid"
    ):
        vid = row["video_id"]
        start = float(row["start"])
        end = float(row["end"])
        if vid in prev and prev[vid] > start:
            overlaps += 1
        prev_end = prev.get(vid)
        prev[vid] = end if prev_end is None else max(prev_end, end)

    measured = f"timestamp_overflow={overflow} max_exc_s={max_exc:.4g} overlap_pairs={overlaps}"
    ok = overflow == 0 and overlaps == 0
    return (_pass if ok else _fail)("L4", measured, "overflow==0 and overlap_pairs==0")


def check_l5(con: sqlite3.Connection, paths: CorpusPaths) -> CheckResult:
    n_empty = scalar(
        con,
        "SELECT COUNT(*) FROM windows WHERE IFNULL(n_syllables,0)=0 AND IFNULL(coverage,0)=0",
    )
    n_empty_c = scalar(
        con,
        "SELECT COUNT(*) FROM windows WHERE IFNULL(n_syllables,0)=0 AND IFNULL(coverage,0)=0 "
        "AND tier='C'",
    )
    n_win = scalar(con, "SELECT COUNT(*) FROM windows")
    stats = load_stats(paths.stats)
    public = None
    flat = flatten_json(stats)
    for k, v in flat.items():
        if k in {"n_windows", "windows", "num_windows"} and isinstance(v, (int, float)):
            public = int(v)
            break
    if public is None:
        public = n_win
    included = n_empty > 0 and public >= n_win and n_win > 0
    measured = (
        f"n_empty={n_empty} n_empty_C={n_empty_c} n_windows={n_win} public_n_windows={public}"
    )
    if n_empty == 0:
        return _pass("L5", measured, "empty==0 or excluded from public total")
    return (_fail if included else _pass)(
        "L5", measured, "empty windows not counted in public total"
    )


def _vad_window_count(paths: CorpusPaths) -> tuple[int | None, bool]:
    """Return (n_vad_windows, has_reason_field)."""
    for p in paths.vad_files:
        try:
            if p.suffix.lower() == ".json":
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    has_reason = any(
                        isinstance(x, dict) and ("reason" in x or "drop_reason" in x)
                        for x in data[:20]
                    )
                    if data and isinstance(data[0], dict) and (
                        "uid" in data[0] or "window_id" in data[0] or "start" in data[0]
                    ):
                        return len(data), has_reason
                    if data and isinstance(data[0], str):
                        return len(data), False
                if isinstance(data, dict):
                    for k in ("windows", "kept", "all", "items"):
                        if isinstance(data.get(k), list):
                            items = data[k]
                            has_reason = any(
                                isinstance(x, dict)
                                and ("reason" in x or "drop_reason" in x)
                                for x in items[:20]
                            )
                            return len(items), has_reason
                    if "n_windows" in data:
                        return int(data["n_windows"]), bool(
                            data.get("discard_reasons") or data.get("reasons")
                        )
            elif p.suffix.lower() == ".csv":
                with p.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    has_reason = bool(
                        reader.fieldnames
                        and any("reason" in c.lower() for c in reader.fieldnames)
                    )
                    return len(rows), has_reason
            elif p.suffix.lower() in {".txt", ".log"}:
                lines = [
                    ln
                    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()
                    if ln.strip()
                ]
                return len(lines), False
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return None, False


def check_l6(con: sqlite3.Connection, paths: CorpusPaths) -> CheckResult:
    n_win = scalar(con, "SELECT COUNT(*) FROM windows")
    db_vids = {r[0] for r in con.execute("SELECT video_id FROM videos")}
    ids: list[str] = []
    if paths.ids_txt and paths.ids_txt.is_file():
        ids = [
            ln.strip()
            for ln in paths.ids_txt.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    missing = [v for v in ids if v not in db_vids]
    n_vad, has_reason = _vad_window_count(paths)
    discarded = None if n_vad is None else n_vad - n_win
    stats = load_stats(paths.stats)
    flat = flatten_json(stats)
    stats_has_discard = any(
        "discard" in k.lower() or "vad" in k.lower() or "drop" in k.lower()
        for k in flat
    )
    stats_has_missing = any(
        "missing" in k.lower() or "disappear" in k.lower() or "dropped_video" in k.lower()
        for k in flat
    )
    if "dropped_videos" in stats or "missing_videos" in stats or "vad" in stats:
        stats_has_discard = True
        if stats.get("missing_videos") or stats.get("dropped_videos"):
            stats_has_missing = True

    measured = (
        f"vad_windows={n_vad} db_windows={n_win} discarded={discarded} "
        f"discard_reason_field={has_reason} ids={len(ids)} missing_videos={len(missing)} "
        f"missing_ids={missing[:5]} stats_records_discard={stats_has_discard} "
        f"stats_records_missing={stats_has_missing}"
    )
    # FAIL if discards lack reasons, or disappeared videos are not in STATS.
    bad_discard = discarded is not None and discarded > 0 and not has_reason
    bad_missing = bool(missing) and not stats_has_missing
    bad_stats = (discarded or missing) and not (stats_has_discard and (not missing or stats_has_missing))
    if n_vad is None and not ids:
        if not stats_has_discard:
            return _fail(
                "L6",
                measured,
                "discard reasons + missing videos recorded in STATS",
            )
        return _skip("L6", measured, "VAD log / ids.txt present with reasons")
    if bad_discard or bad_missing or bad_stats:
        return _fail(
            "L6",
            measured,
            "discard reason field/log; disappeared videos in STATS",
        )
    return _pass(
        "L6",
        measured,
        "discard reason field/log; disappeared videos in STATS",
    )


# ---------------------------------------------------------------------------
# T checks
# ---------------------------------------------------------------------------


def check_t1(con: sqlite3.Connection, paths: CorpusPaths) -> CheckResult:
    sum_dur = scalar(con, "SELECT IFNULL(SUM(dur),0) FROM windows")
    sum_speech = scalar(con, "SELECT IFNULL(SUM(speech_s),0) FROM videos")
    sum_ab = scalar(
        con, "SELECT IFNULL(SUM(dur),0) FROM windows WHERE tier IN ('A','B')"
    )
    h_dur = float(sum_dur) / 3600.0
    h_speech = float(sum_speech) / 3600.0
    h_ab = float(sum_ab) / 3600.0
    stats = load_stats(paths.stats)
    claimed = None
    for k in (
        "speech_h",
        "hours",
        "duration_h",
        "headline_hours",
        "speech_hours",
        "n_hours",
    ):
        if k in stats and isinstance(stats[k], (int, float)):
            claimed = float(stats[k])
            break
    if claimed is None:
        for p in paths.readmes:
            text = _read_text_head(p, 40_000)
            m = HOURS_RE.search(text)
            if m:
                claimed = float(m.group(1))
                break
    if claimed is None:
        # STATS headline is videos.speech_s (Sep-18: 16.36h).
        claimed = round(h_speech, 2) if h_speech else h_speech
    measured = (
        f"sum(windows.dur)={h_dur:.3f}h(incl padding) "
        f"sum(videos.speech_s)={h_speech:.3f}h(STATS headline) "
        f"A+B actual speech={h_ab:.3f}h claimed={claimed:.3f}h"
    )
    # Public claim must equal A+B actual speech, not the STATS headline.
    ok = abs(float(claimed) - h_ab) <= 0.005
    return (_pass if ok else _fail)(
        "T1",
        measured,
        "claimed hours == A+B actual speech (not speech_s headline)",
    )


def check_t3(paths: CorpusPaths) -> CheckResult:
    # Meta-check (AUDIT-SPEC): do not copy 10_validate tautologies. Always PASS.
    note = "audit does not copy 10_validate tautologies"
    if paths.validate_10 and paths.validate_10.is_file():
        note += f"; saw {paths.validate_10.name}"
    return _pass("T3", note, "meta PASS (do not replicate always-true asserts)")


def check_t4(con: sqlite3.Connection, paths: CorpusPaths) -> CheckResult:
    if paths.stats is None or not paths.stats.is_file():
        return _skip("T4", "STATS.json missing", "nine counts == DB")
    stats = load_stats(paths.stats)
    flat = flatten_json(stats)
    mismatches: list[str] = []
    matched = 0
    details: list[str] = []
    for canon, sql, aliases in STATS_COUNT_SPECS:
        db_n = int(scalar(con, sql) or 0)
        found = None
        found_key = None
        for a in aliases:
            if a in flat and isinstance(flat[a], (int, float)) and not isinstance(
                flat[a], bool
            ):
                found = int(flat[a])
                found_key = a
                break
            # case-insensitive / nested path endswith
            for k, v in flat.items():
                if k.split(".")[-1].lower() == a.lower() and isinstance(v, (int, float)):
                    found = int(v)
                    found_key = k
                    break
            if found is not None:
                break
        if found is None:
            details.append(f"{canon}=DB{db_n}/missing")
            mismatches.append(canon)
            continue
        matched += 1
        if found != db_n:
            mismatches.append(f"{found_key}:{found}!={db_n}")
        details.append(f"{canon}={found}")
    measured = f"matched={matched}/9 mismatches={len(mismatches)} {','.join(details)}"
    if matched == 9 and not mismatches:
        return _pass("T4", measured, "all nine STATS counts == DB")
    if matched and not mismatches:
        return _pass("T4", measured, "STATS counts == DB")
    return _fail("T4", measured, "all nine STATS counts == DB")


# ---------------------------------------------------------------------------
# R checks (--round 2)
# ---------------------------------------------------------------------------


def load_sheet(path: Path) -> tuple[bytes, list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    cols = list(reader.fieldnames or [])
    rows = list(reader)
    return raw, cols, rows


def check_r1(con: sqlite3.Connection, sheet_rows: list[dict[str, str]]) -> CheckResult:
    ids = [r.get("window_id", "") for r in sheet_rows]
    if not ids:
        return _fail("R1", "n_sheet=0", "tier_not_AB==0")
    placeholders = ",".join("?" * len(ids))
    rows = list(
        con.execute(
            f"SELECT uid, tier FROM windows WHERE uid IN ({placeholders})", ids
        )
    )
    by = {r["uid"]: r["tier"] for r in rows}
    n_missing = sum(1 for i in ids if i not in by)
    n_not_ab = sum(1 for i in ids if by.get(i) not in (None, "A", "B") and i in by)
    measured = f"tier_not_AB={n_not_ab}/{len(ids)} unmatched={n_missing}"
    return (_pass if n_not_ab == 0 else _fail)("R1", measured, "tier_not_AB==0")


def check_r2(con: sqlite3.Connection, sheet_rows: list[dict[str, str]]) -> CheckResult:
    ids = [r.get("window_id", "") for r in sheet_rows]
    if not ids:
        return _fail("R2", "n_sheet=0", "lang_not_yue==0")
    placeholders = ",".join("?" * len(ids))
    rows = list(
        con.execute(
            f"SELECT uid, lang FROM windows WHERE uid IN ({placeholders})", ids
        )
    )
    by = {r["uid"]: r["lang"] for r in rows}
    n = sum(1 for i in ids if i in by and by[i] != "yue")
    measured = f"lang_not_yue={n}/{len(ids)}"
    return (_pass if n == 0 else _fail)("R2", measured, "lang_not_yue==0")


def check_r3(con: sqlite3.Connection, sheet_rows: list[dict[str, str]]) -> CheckResult:
    ids_bh = [r.get("window_id", "") for r in sheet_rows if r.get("stratum") == "both_high"]
    n_bh = len(ids_bh)
    n_c = 0
    if ids_bh:
        placeholders = ",".join("?" * len(ids_bh))
        n_c = scalar(
            con,
            f"SELECT COUNT(*) FROM windows WHERE uid IN ({placeholders}) AND tier='C'",
            tuple(ids_bh),
        )
    n_flag = scalar(con, "SELECT COUNT(*) FROM windows WHERE IFNULL(flag_sing,0)=1")
    measured = f"both_high_C={n_c}/{n_bh} corpus_flag_sing1={n_flag}"
    return (_pass if n_c == 0 else _fail)("R3", measured, "both_high∩C==0")


def check_r4(raw: bytes, cols: list[str], rows: list[dict[str, str]]) -> CheckResult:
    problems: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("BOM")
    if b"\r\n" in raw or b"\r" in raw:
        problems.append("not_LF")
    if cols != SHEET_COLUMNS:
        problems.append(f"columns={cols}")
    bad_labels = sorted(
        {r.get("human_label", "") for r in rows} - HUMAN_LABELS - {""}
    )
    if bad_labels:
        problems.append(f"labels={bad_labels}")
    measured = f"rows={len(rows)} problems={problems or 'none'}"
    return (_pass if not problems else _fail)(
        "R4",
        measured,
        "cols=SHEET_COLUMNS; human_label in six values; UTF-8 no BOM; LF",
    )


def _parse_round2_commits(text: str) -> tuple[str | None, str | None]:
    pred = None
    result = None
    for line in text.splitlines():
        if "预测" in line and "commit" in line.lower():
            m = SHA_RE.search(line)
            if m:
                pred = m.group(1)
        if re.search(r"结果 commit", line, re.I) or (
            "结果" in line and "commit" in line.lower() and "预测" not in line
        ):
            m = SHA_RE.search(line)
            if m:
                result = m.group(1)
    return pred, result


def check_r5(analysis_root: Path) -> CheckResult:
    md = analysis_root / "rounds/ROUND-2.md"
    if not md.is_file():
        return _skip("R5", "rounds/ROUND-2.md missing", "prediction is ancestor of result")
    pred, result = _parse_round2_commits(_read_text(md))
    if not pred or not result:
        return _fail(
            "R5",
            f"prediction={pred} result={result}",
            "both commits parsed; merge-base --is-ancestor",
        )
    git_dir = analysis_root / ".git"
    if not git_dir.exists():
        return _skip(
            "R5",
            f"prediction={pred} result={result} git=missing",
            "prediction is ancestor of result",
        )
    proc = subprocess.run(
        ["git", "-C", str(analysis_root), "merge-base", "--is-ancestor", pred, result],
        capture_output=True,
        text=True,
    )
    measured = f"prediction={pred} result={result} is-ancestor_exit={proc.returncode}"
    return (_pass if proc.returncode == 0 else _fail)(
        "R5", measured, "git merge-base --is-ancestor prediction result"
    )


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def run_audit(
    icanto_root: Path | None,
    analysis_root: Path,
    round_n: int | None,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    paths: CorpusPaths | None = None
    con: sqlite3.Connection | None = None
    if icanto_root is None:
        for cid in CHECK_IDS_CORPUS:
            results.append(_skip(cid, "ICANTO_ROOT unset", "env ICANTO_ROOT points at corpus"))
    else:
        paths = discover_corpus(icanto_root)
        if paths.sqlite is None:
            for cid in CHECK_IDS_CORPUS:
                results.append(
                    _skip(cid, f"sqlite missing under {icanto_root}", "corpus.sqlite present")
                )
        else:
            con = open_ro(paths.sqlite)
            results.append(_run_check("C1", lambda: check_c1(con, paths)))
            results.append(_run_check("C2", lambda: check_c2(con)))
            results.append(_run_check("C3", lambda: check_c3(con)))
            results.append(_run_check("C4", lambda: check_c4(con)))
            results.append(_run_check("C5", lambda: check_c5(con)))
            results.append(_run_check("C6", lambda: check_c6(con)))
            results.append(_run_check("C7", lambda: check_c7(con)))
            results.append(_run_check("C8", lambda: check_c8(con, paths)))
            results.append(_run_check("C9", lambda: check_c9(paths)))
            results.append(_run_check("C13", lambda: check_c13(con, paths)))
            results.append(_run_check("L1", lambda: check_l1(paths)))
            results.append(_run_check("L2", lambda: check_l2(con)))
            results.append(_run_check("L3", lambda: check_l3(con)))
            results.append(_run_check("L4", lambda: check_l4(con)))
            results.append(_run_check("L5", lambda: check_l5(con, paths)))
            results.append(_run_check("L6", lambda: check_l6(con, paths)))
            results.append(_run_check("T1", lambda: check_t1(con, paths)))
            results.append(_run_check("T3", lambda: check_t3(paths)))
            results.append(_run_check("T4", lambda: check_t4(con, paths)))

    if round_n == 2:
        sheet_path = analysis_root / "ROUND-2" / "listening_sheet.csv"
        if not sheet_path.is_file():
            for cid in CHECK_IDS_ROUND2:
                results.append(
                    _skip(cid, f"missing {sheet_path}", "ROUND-2/listening_sheet.csv")
                )
        else:
            raw, cols, rows = load_sheet(sheet_path)
            if con is None:
                for cid in ("R1", "R2", "R3"):
                    results.append(_skip(cid, "no sqlite to join", "join windows on uid"))
            else:
                results.append(_run_check("R1", lambda: check_r1(con, rows)))
                results.append(_run_check("R2", lambda: check_r2(con, rows)))
                results.append(_run_check("R3", lambda: check_r3(con, rows)))
            results.append(_run_check("R4", lambda: check_r4(raw, cols, rows)))
            results.append(_run_check("R5", lambda: check_r5(analysis_root)))

    if con is not None:
        con.close()
    return results


def print_results(results: list[CheckResult]) -> int:
    for r in results:
        print(r.line())
    n_fail = sum(1 for r in results if r.status == "FAIL")
    n_pass = sum(1 for r in results if r.status == "PASS")
    n_skip = sum(1 for r in results if r.status == "SKIP")
    print(f"SUMMARY pass={n_pass} fail={n_fail} skip={n_skip}")
    return 1 if n_fail else 0


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _init_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            upload_date TEXT,
            n_windows INT,
            speech_s REAL
        );
        CREATE TABLE windows (
            uid TEXT PRIMARY KEY,
            video_id TEXT,
            idx INT,
            start REAL,
            end REAL,
            dur REAL,
            start_sample INT,
            end_sample INT,
            boundary_start TEXT,
            boundary_end TEXT,
            lang TEXT,
            text_raw TEXT,
            text_norm TEXT,
            text_clean TEXT,
            flag_hai INT,
            flag_simp INT,
            flag_sing INT,
            flag_boiler INT,
            chars_per_sec REAL,
            aligned INT,
            coverage REAL,
            first_s REAL,
            in_range INT,
            max_zero_run INT,
            tone_shift_suspect INT,
            n_syllables INT,
            tier TEXT,
            text_human TEXT
        );
        CREATE TABLE syllables (
            syl_id TEXT PRIMARY KEY,
            uid TEXT,
            video_id TEXT,
            pos INT,
            char TEXT,
            start REAL,
            end REAL,
            dur REAL,
            tier TEXT,
            jp_default TEXT,
            jp_ctx TEXT,
            jp_realized TEXT,
            jp_match TEXT
        );
        CREATE TABLE runs (run_id INTEGER, built_at TEXT);
        """
    )


def _win(
    uid: str,
    video_id: str,
    idx: int,
    *,
    start: float,
    end: float,
    lang: str = "yue",
    text: str = "hello",
    flag_sing: int = 0,
    flag_boiler: int = 0,
    flag_simp: int = 0,
    cps: float = 2.5,
    aligned: int = 1,
    coverage: float = 0.95,
    in_range: int = 1,
    n_syllables: int = 1,
    tier: str,
) -> tuple[Any, ...]:
    return (
        uid,
        video_id,
        idx,
        start,
        end,
        end - start,
        0,
        0,
        "pause",
        "pause",
        lang,
        text,
        text,
        text,
        0,
        flag_simp,
        flag_sing,
        flag_boiler,
        cps,
        aligned,
        coverage,
        0.0,
        in_range,
        0,
        0,
        n_syllables,
        tier,
        None,
    )


def _syl(
    syl_id: str,
    uid: str,
    video_id: str,
    pos: int,
    *,
    start: float,
    end: float,
    tier: str,
    jp_realized: str = "nei5",
    jp_match: str = "exact_default",
    char: str = "你",
) -> tuple[Any, ...]:
    return (
        syl_id,
        uid,
        video_id,
        pos,
        char,
        start,
        end,
        end - start,
        tier,
        "nei5",
        "nei5",
        jp_realized,
        jp_match,
    )


COMMON_PY = '''"""Fixture equivalent of corpus common.tier_of (C7 + boiler/simp)."""

def _get(w, k, default=None):
    if isinstance(w, dict):
        return w.get(k, default)
    if hasattr(w, "keys"):
        try:
            if k in w.keys():
                return w[k]
        except Exception:
            pass
    return getattr(w, k, default)


def tier_of(w):
    lang = _get(w, "lang")
    try:
        flag_sing = int(_get(w, "flag_sing") or 0)
    except (TypeError, ValueError):
        flag_sing = 0
    try:
        cps = float(_get(w, "chars_per_sec") or 0.0)
    except (TypeError, ValueError):
        cps = 0.0
    cov = _get(w, "coverage")
    try:
        coverage = float(cov) if cov is not None else 1.0
    except (TypeError, ValueError):
        coverage = 1.0
    ir = _get(w, "in_range")
    try:
        in_range = int(ir) if ir is not None else 1
    except (TypeError, ValueError):
        in_range = 1
    if lang != "yue" or flag_sing == 1 or cps > 8 or coverage < 0.2 or in_range == 0:
        return "C"
    try:
        boiler = int(_get(w, "flag_boiler") or 0)
    except (TypeError, ValueError):
        boiler = 0
    try:
        simp = int(_get(w, "flag_simp") or 0)
    except (TypeError, ValueError):
        simp = 0
    if boiler or simp:
        return "B"
    return "A"
'''

EXPORT_09_PY = '''EXPORT_SQL = """
SELECT s.syl_id, s.uid, s.video_id, s.pos, s.char, s.start, s.end, s.dur, s.tier,
       s.jp_default, s.jp_ctx, s.jp_realized, s.jp_match
FROM syllables s
JOIN windows w ON w.uid = s.uid
WHERE w.tier IN ('A', 'B')
ORDER BY s.syl_id
"""
'''

VALIDATE_10_PY = '''"""Intentionally tautological asserts (audit must not copy these)."""
assert True
assert 1 in (0, 1)
'''

REVIEW_12_PY = '''FRAME_SQL = """
SELECT s.syl_id FROM syllables s
JOIN windows w ON w.uid = s.uid
WHERE w.tier IN ('A','B') AND IFNULL(s.dur,0)>0
"""
REPORTED_N = {reported}
'''


def write_fixture_tree(root: Path, kind: str = "mixed") -> Path:
    """Write a mini ICANTO_ROOT + ANALYSIS_ROOT under ``root``.

    kind='mixed': known-style FAILs (expected values not weakened).
    kind='clean': all implemented checks PASS.
    """
    icanto = root / "icanto"
    analysis = root / "analysis"
    work = icanto / "corpus" / "dataset_v2" / "work"
    scripts = icanto / "scripts"
    work.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    (analysis / "ROUND-2").mkdir(parents=True, exist_ok=True)
    (analysis / "rounds").mkdir(parents=True, exist_ok=True)

    db_path = work / "corpus.sqlite"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    _init_schema(con)

    subscribe = "如果覺得內容啱睇嘅subscribe"
    if kind == "clean":
        windows = [
            _win("vAA_000", "vAA", 0, start=0, end=4, text="alpha one", n_syllables=1, tier="A"),
            _win("vAA_001", "vAA", 1, start=4, end=8, text="alpha two", n_syllables=1, tier="A", aligned=0),
            _win(
                "vBB_000",
                "vBB",
                0,
                start=0,
                end=5,
                text="beta boiler",
                flag_boiler=1,
                n_syllables=1,
                tier="B",
            ),
            _win(
                "vCC_000",
                "vCC",
                0,
                start=0,
                end=3,
                lang="zh",
                text="不是粤语",
                n_syllables=1,
                tier="C",
            ),
        ]
        syllables = [
            _syl("s1", "vAA_000", "vAA", 0, start=0.1, end=0.4, tier="A"),
            _syl("s2", "vAA_001", "vAA", 0, start=4.1, end=4.4, tier="A"),
            _syl("s3", "vBB_000", "vBB", 0, start=0.2, end=0.5, tier="B"),
            _syl("s4", "vCC_000", "vCC", 0, start=0.1, end=0.3, tier="C"),
        ]
        videos = [
            ("vAA", "video A", "20240101", 2, 8.0),
            ("vBB", "video B", "20240102", 1, 5.0),
            ("vCC", "video C", "20240103", 1, 3.0),
        ]
    else:
        windows = [
            _win("vAA_000", "vAA", 0, start=0.0, end=10.0, text=subscribe, n_syllables=2, tier="A"),
            _win(
                "vAA_001",
                "vAA",
                1,
                start=9.0,
                end=20.0,
                text=subscribe,
                n_syllables=2,
                tier="A",
                coverage=1.5,
            ),
            _win("vDD_000", "vDD", 0, start=0.0, end=4.0, text=subscribe, n_syllables=1, tier="A"),
            _win(
                "vBB_000",
                "vBB",
                0,
                start=0.0,
                end=6.0,
                text="shared dup",
                flag_boiler=1,
                n_syllables=1,
                tier="B",
            ),
            _win(
                "vBB_001",
                "vBB",
                1,
                start=6.0,
                end=12.0,
                text="shared dup",
                flag_simp=1,
                n_syllables=1,
                tier="B",
            ),
            _win(
                "vCC_000",
                "vCC",
                0,
                start=0.0,
                end=3.0,
                lang="zh",
                text="忘不了你的錯",
                n_syllables=1,
                tier="C",
            ),
            _win(
                "vCC_001",
                "vCC",
                1,
                start=3.0,
                end=6.0,
                text="sing",
                flag_sing=1,
                n_syllables=0,
                coverage=0.0,
                tier="C",
            ),
        ]
        syllables = [
            _syl("s1", "vAA_000", "vAA", 0, start=-1.0, end=0.2, tier="A"),  # overflow
            _syl(
                "s2",
                "vAA_000",
                "vAA",
                1,
                start=0.2,
                end=0.2,
                tier="A",
                jp_realized="",
                jp_match="none",
            ),  # C3 + C4 (dur=0)
            _syl("s3", "vAA_001", "vAA", 0, start=9.1, end=9.4, tier="A"),
            _syl("s4", "vAA_001", "vAA", 1, start=9.4, end=9.7, tier="A"),
            _syl("s5", "vDD_000", "vDD", 0, start=0.1, end=0.4, tier="A"),
            _syl("s6", "vBB_000", "vBB", 0, start=0.1, end=0.4, tier="B"),
            _syl("s7", "vBB_001", "vBB", 0, start=6.1, end=6.4, tier="B"),
            _syl("s8", "vCC_000", "vCC", 0, start=0.1, end=0.3, tier="C"),
        ]
        videos = [
            ("vAA", "video A", "20240101", 2, 40.0),
            ("vBB", "video B", "20240102", 2, 20.0),
            ("vCC", "video C", "20240103", 2, 10.0),
            ("vDD", "video D", "20240104", 1, 8.0),
        ]

    con.executemany("INSERT INTO videos VALUES (?,?,?,?,?)", videos)
    con.executemany(
        "INSERT INTO windows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        windows,
    )
    con.executemany(
        "INSERT INTO syllables VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        syllables,
    )
    con.execute("INSERT INTO runs VALUES (1, '2026-09-18')")
    con.commit()

    n_videos = scalar(con, "SELECT COUNT(*) FROM videos")
    n_windows = scalar(con, "SELECT COUNT(*) FROM windows")
    n_syllables = scalar(con, "SELECT COUNT(*) FROM syllables")
    n_wa = scalar(con, "SELECT COUNT(*) FROM windows WHERE tier='A'")
    n_wb = scalar(con, "SELECT COUNT(*) FROM windows WHERE tier='B'")
    n_wc = scalar(con, "SELECT COUNT(*) FROM windows WHERE tier='C'")
    n_sa = scalar(con, "SELECT COUNT(*) FROM syllables WHERE tier='A'")
    n_sb = scalar(con, "SELECT COUNT(*) FROM syllables WHERE tier='B'")
    n_sc = scalar(con, "SELECT COUNT(*) FROM syllables WHERE tier='C'")
    n_ab_syl = n_sa + n_sb
    n_frame = scalar(
        con,
        "SELECT COUNT(*) FROM syllables s JOIN windows w ON s.uid=w.uid "
        "WHERE w.tier IN ('A','B') AND IFNULL(s.dur,0)>0",
    )
    sum_ab = scalar(con, "SELECT IFNULL(SUM(dur),0) FROM windows WHERE tier IN ('A','B')")
    h_ab = float(sum_ab) / 3600.0
    h_speech = float(scalar(con, "SELECT IFNULL(SUM(speech_s),0) FROM videos")) / 3600.0

    # C8 CSV
    sql_rows = list(
        con.execute(
            "SELECT s.syl_id, s.uid, s.video_id, s.pos, s.char, s.start, s.end, s.dur, s.tier, "
            "s.jp_default, s.jp_ctx, s.jp_realized, s.jp_match "
            "FROM syllables s JOIN windows w ON w.uid=s.uid "
            "WHERE w.tier IN ('A','B') ORDER BY s.syl_id"
        )
    )
    cols = [
        "syl_id",
        "uid",
        "video_id",
        "pos",
        "char",
        "start",
        "end",
        "dur",
        "tier",
        "jp_default",
        "jp_ctx",
        "jp_realized",
        "jp_match",
    ]
    pub_dir = icanto / "corpus" / "dataset_v2" / "dataset_v2"
    if kind == "clean":
        csv_path = icanto / "corpus" / "dataset_v2" / "syllables_AB.csv"
    else:
        pub_dir.mkdir(parents=True, exist_ok=True)
        csv_path = pub_dir / "syllables_AB.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for i, r in enumerate(sql_rows):
            d = {c: r[c] for c in cols}
            if kind != "clean" and i == 0 and d["start"] is not None:
                d["start"] = float(d["start"]) + 0.01
            w.writerow(d)

    con.close()

    _write(scripts / "common.py", COMMON_PY)
    _write(scripts / "09_export.py", EXPORT_09_PY)
    _write(scripts / "10_validate.py", VALIDATE_10_PY)
    reported = n_frame if kind == "clean" else n_ab_syl
    _write(scripts / "12_review_sample.py", REVIEW_12_PY.format(reported=reported))

    if kind == "clean":
        _write(
            icanto / "README.md",
            "Release lives in dataset_v2/ (work sqlite + syllables_AB.csv).\n"
            f"A+B speech {h_ab:.3f}h\n",
        )
        stats_hours = h_ab
        channels = ["@icantonese", "@other"]
        vad = [
            {"uid": "vAA_000", "keep": True},
            {"uid": "vAA_001", "keep": True},
            {"uid": "vBB_000", "keep": True},
            {"uid": "vCC_000", "keep": True},
        ]
        ids = ["vAA", "vBB", "vCC"]
        stats_extra: dict[str, Any] = {}
        sheet_rows = [
            {
                "window_id": "vAA_000",
                "video_id": "vAA",
                "film_flag": "0",
                "clap_sing": "0.1",
                "singing_prob": "0.1",
                "var_db": "1.0",
                "stratum": "both_high",
                "human_label": "unset",
                "annotator_note": "",
                "forced_flag_sing": "0",
            },
            {
                "window_id": "vAA_001",
                "video_id": "vAA",
                "film_flag": "0",
                "clap_sing": "0.0",
                "singing_prob": "0.0",
                "var_db": "1.0",
                "stratum": "both_low",
                "human_label": "unset",
                "annotator_note": "",
                "forced_flag_sing": "0",
            },
        ]
    else:
        _write(
            icanto / "README.md",
            "Published set is in dataset_v2/.\n"
            f"Corpus hours: {h_speech:.2f}h\n"
            f"发布 {n_ab_syl} syllables\n",
        )
        stats_hours = round(h_speech, 2)
        channels = ["@icantonese"]
        vad = [{"uid": w[0], "keep": True} for w in windows] + [
            {"uid": "dropped_001", "keep": False},
            {"uid": "dropped_002", "keep": False},
        ]
        ids = ["vAA", "vBB", "vCC", "vDD", "YJ-WX_ES5Jc"]
        stats_extra = {}
        sheet_rows = [
            {
                "window_id": "vCC_000",
                "video_id": "vCC",
                "film_flag": "1",
                "clap_sing": "5.0",
                "singing_prob": "0.9",
                "var_db": "1.0",
                "stratum": "both_high",
                "human_label": "unset",
                "annotator_note": "",
                "forced_flag_sing": "0",
            },
            {
                "window_id": "vAA_000",
                "video_id": "vAA",
                "film_flag": "0",
                "clap_sing": "-3.0",
                "singing_prob": "0.001",
                "var_db": "1.0",
                "stratum": "both_low",
                "human_label": "unset",
                "annotator_note": "",
                "forced_flag_sing": "0",
            },
            {
                "window_id": "vCC_001",
                "video_id": "vCC",
                "film_flag": "1",
                "clap_sing": "1.0",
                "singing_prob": "0.2",
                "var_db": "1.0",
                "stratum": "mid",
                "human_label": "unset",
                "annotator_note": "",
                "forced_flag_sing": "1",
            },
        ]

    stats_obj = {
        "n_videos": n_videos,
        "n_windows": n_windows,
        "n_syllables": n_syllables,
        "n_windows_A": n_wa,
        "n_windows_B": n_wb,
        "n_windows_C": n_wc,
        "n_syllables_A": n_sa,
        "n_syllables_B": n_sb,
        "n_syllables_C": n_sc,
        "speech_h": stats_hours,
        **stats_extra,
    }
    _write(icanto / "STATS.json", json.dumps(stats_obj, indent=2) + "\n")
    _write(icanto / "ids.txt", "\n".join(ids) + "\n")
    _write(icanto / "vad" / "windows.json", json.dumps(vad, indent=2) + "\n")
    info_videos = [v[0] for v in videos]
    for i, vid in enumerate(info_videos):
        ch = channels[i % len(channels)]
        _write(
            icanto / "videos" / vid / "info.json",
            json.dumps({"id": vid, "channel_id": ch}, indent=2) + "\n",
        )

    sheet_path = analysis / "ROUND-2" / "listening_sheet.csv"
    with sheet_path.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS, lineterminator="\n")
        w.writeheader()
        for row in sheet_rows:
            w.writerow(row)

    # Present for R4/R1–R3 smoke. R5 needs a git repo (self-test creates one).
    _write(
        analysis / "rounds" / "ROUND-2.md",
        "- 预测 commit：`fffad05152daaf603bef1d99f9e931831b04e0a6`\n"
        "- 结果 commit：`6b76d2cb1ab42957671647095a91c0017f79792a`\n",
    )
    _write(
        root / "README.md",
        "# Audit fixtures\n\n"
        "Mixed mini-corpus for `scripts/audit.py` smoke. It is **supposed** to FAIL\n"
        "the same classes of checks as the 2026-09-18 corpus. Expected values stay\n"
        "at the spec (e.g. `== 0`); they are not relaxed to match measured counts.\n\n"
        "```bash\n"
        "ICANTO_ROOT=fixtures/audit/icanto \\\n"
        "ANALYSIS_ROOT=fixtures/audit/analysis \\\n"
        "python scripts/audit.py --round 2\n"
        "```\n\n"
        "`python scripts/audit.py --self-test` is the green bar.\n",
    )

    return root


def _git_init_with_commits(repo: Path) -> tuple[str, str]:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "audit@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "audit"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "marker.txt").write_text("pred\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "prediction"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    pred = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    (repo / "marker.txt").write_text("result\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "result"], cwd=repo, check=True, capture_output=True
    )
    result = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    return pred, result


def _write_round2_md(analysis: Path, pred: str, result: str) -> None:
    _write(
        analysis / "rounds" / "ROUND-2.md",
        f"- 预测 commit：`{pred}`\n- 结果 commit：`{result}`\n",
    )


def _by_id(results: list[CheckResult]) -> dict[str, CheckResult]:
    return {r.check_id: r for r in results}


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"SELF-TEST FAILED: {msg}")


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="audit_selftest_") as tmp:
        tmp_path = Path(tmp)
        mixed = write_fixture_tree(tmp_path / "mixed", kind="mixed")
        clean = write_fixture_tree(tmp_path / "clean", kind="clean")

        pred, result = _git_init_with_commits(clean / "analysis")
        _write_round2_md(clean / "analysis", pred, result)
        pred_m, result_m = _git_init_with_commits(mixed / "analysis")
        _write_round2_md(mixed / "analysis", pred_m, result_m)

        os.environ["ICANTO_ROOT"] = str(clean / "icanto")
        os.environ["ANALYSIS_ROOT"] = str(clean / "analysis")
        clean_res = run_audit(clean / "icanto", clean / "analysis", round_n=2)
        clean_map = _by_id(clean_res)
        for cid in CHECK_IDS_CORPUS + CHECK_IDS_ROUND2:
            r = clean_map.get(cid)
            _assert(r is not None, f"clean missing {cid}")
            _assert(
                r.status == "PASS",
                f"clean {cid} expected PASS got {r.line()}",
            )

        os.environ["ICANTO_ROOT"] = str(mixed / "icanto")
        os.environ["ANALYSIS_ROOT"] = str(mixed / "analysis")
        mixed_res = run_audit(mixed / "icanto", mixed / "analysis", round_n=2)
        mixed_map = _by_id(mixed_res)

        # Known-style failures must still use the spec expected values (not washed to reality).
        expect_fail = {
            "C3": "== 0",
            "C4": "== 0",
            "C5": "== 0",
            "C6": "nuniq > 1",
            "C8": "diffs==0",
            "C9": "README path matches",
            "C13": "reported == sampling-frame",
            "L1": "n_channels!=1",
            "L2": "<= 2",
            "L3": "dup_groups==0",
            "L4": "overflow==0",
            "L5": "not counted",
            "L6": "discard reason",
            "T1": "A+B actual speech",
            "R1": "tier_not_AB==0",
            "R2": "lang_not_yue==0",
            "R3": "both_high∩C==0",
        }
        for cid, needle in expect_fail.items():
            r = mixed_map[cid]
            _assert(r.status == "FAIL", f"mixed {cid} expected FAIL got {r.line()}")
            _assert(
                needle.lower() in r.expected.lower() or needle in r.expected,
                f"mixed {cid} expected-text missing {needle!r}: {r.expected}",
            )
            # Do not weaken C3/C4/C5 expected=0 to match measured reality.
            if cid in {"C3", "C4", "C5"}:
                _assert(
                    "== 0" in r.expected,
                    f"{cid} expected was weakened: {r.expected}",
                )

        for cid in ("C1", "C2", "C7", "T3", "T4", "R4", "R5"):
            r = mixed_map[cid]
            _assert(r.status == "PASS", f"mixed {cid} expected PASS got {r.line()}")

        # Independence: all IDs present even when several FAIL.
        _assert(
            [r.check_id for r in mixed_res]
            == CHECK_IDS_CORPUS + CHECK_IDS_ROUND2,
            "check order/completeness",
        )

        # Without --round, R* must not run.
        no_r = run_audit(mixed / "icanto", mixed / "analysis", round_n=None)
        _assert(all(r.check_id not in CHECK_IDS_ROUND2 for r in no_r), "R* leaked")

        # Read-only: sqlite mtime unchanged.
        db = mixed / "icanto/corpus/dataset_v2/work/corpus.sqlite"
        mtime = db.stat().st_mtime
        run_audit(mixed / "icanto", mixed / "analysis", round_n=2)
        _assert(db.stat().st_mtime == mtime, "sqlite mutated")

        # Output format.
        for r in mixed_res:
            line = r.line()
            _assert(
                line.startswith(("PASS ", "FAIL ", "SKIP ")),
                f"bad prefix {line}",
            )
            _assert(" (expected: " in line and line.endswith(")"), f"bad format {line}")

        # R5 FAIL when prediction is not an ancestor.
        _write_round2_md(mixed / "analysis", result_m, pred_m)
        bad_r5 = _by_id(run_audit(mixed / "icanto", mixed / "analysis", round_n=2))["R5"]
        _assert(bad_r5.status == "FAIL", f"R5 reversed should FAIL: {bad_r5.line()}")

        # Missing ICANTO_ROOT → SKIP, no crash.
        skipped = run_audit(None, mixed / "analysis", round_n=None)
        _assert(all(r.status == "SKIP" for r in skipped), "unset root should SKIP")

        # C6 expected stays '> 1' even when measured nuniq is 1.
        _assert("nuniq > 1" in mixed_map["C6"].expected, "C6 expected washed")

    print("SELF-TEST PASSED", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read-only process audit (docs/AUDIT-SPEC.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment:
  ICANTO_ROOT     corpus root (sqlite, scripts, STATS.json, info.json)
  ANALYSIS_ROOT   analysis repo root (ROUND-2/, rounds/)

Examples:
  python scripts/audit.py --self-test

  ICANTO_ROOT=fixtures/audit/icanto ANALYSIS_ROOT=fixtures/audit/analysis \\
    python scripts/audit.py --round 2

  ICANTO_ROOT=/workspace/cantoai ANALYSIS_ROOT=. python scripts/audit.py --round 2
""",
    )
    p.add_argument(
        "--round",
        type=int,
        default=None,
        metavar="N",
        help="Also run round-specific checks (2 = listening sheet R1–R5)",
    )
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Temp fixtures: PASS tree, FAIL tree (expected values not weakened)",
    )
    p.add_argument(
        "--write-fixtures",
        action="store_true",
        help="Write fixtures/audit/{icanto,analysis} mixed tree and exit 0",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        run_self_test()
        return 0
    if args.write_fixtures:
        dest = Path(__file__).resolve().parents[1] / "fixtures" / "audit"
        if dest.exists():
            import shutil

            shutil.rmtree(dest)
        write_fixture_tree(dest, kind="mixed")
        print(f"wrote {dest}", flush=True)
        return 0
    if args.round is not None and args.round != 2:
        print(f"WARN round={args.round} has no extra checks (only 2 is defined)", file=sys.stderr)
    icanto = env_path("ICANTO_ROOT")
    analysis = analysis_root_from_env()
    results = run_audit(icanto.resolve() if icanto else None, analysis, args.round)
    return print_results(results)


if __name__ == "__main__":
    sys.exit(main())
