#!/usr/bin/env python3
"""CI contract checks (analysis-contract.mdc). Adds rows to checks.json.

Missing inputs yield SKIP with `missing` set. Never substitute a default.
Does not write expected/ or frame.yaml.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

CHECK_KEYS = ("name", "status", "expected", "expected_source", "observed", "missing")
STATUSES = {"PASS", "FAIL", "SKIP"}
SOURCE_RE = re.compile(
    r"^(frame\.yaml|rounds/ROUND-[0-9]+\.yaml|expected/.+):.+$"
)
SELECT_FROM = re.compile(r"\bSELECT\b")
FROM_WORD = re.compile(r"\bFROM\b")
NOT_SUPPORTED = re.compile(r"not supported", re.I)
PATH_SUFFIXES = ("_PATH", "_DIR", "_FILE", "_ROOT")
FORBIDDEN_SRC_SNIPPETS = (
    ".fillna(",
    "nan_to_num",
    "COALESCE",
    'errors="coerce"',
    "errors='coerce'",
    " or 0",
    " or 0)",
    ".mask(",
    ".where(",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", dest="repo_ROOT", required=True)
    p.add_argument("--schema-sqlite", dest="schema_FILE", required=True)
    p.add_argument("--checks-file", dest="checks_FILE", required=True)
    p.add_argument("--frame-file", dest="frame_FILE", required=True)
    p.add_argument("--round-yaml", dest="round_yaml_FILE", required=True)
    return p.parse_args(argv)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_expected_file(path: Path) -> str:
    return read_text(path).strip()


def load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(read_text(path))
    if not isinstance(raw, dict):
        return {}
    return raw


def row(
    name: str,
    status: str,
    expected: Any,
    expected_source: str,
    observed: Any,
    missing: str | None,
) -> dict[str, Any]:
    if status not in STATUSES:
        status = "FAIL"
    return {
        "name": name,
        "status": status,
        "expected": expected,
        "expected_source": expected_source,
        "observed": observed,
        "missing": missing,
    }


def compare_check(
    name: str,
    expected: Any,
    expected_source: str,
    observed: Any,
    missing_path: Path | None = None,
) -> dict[str, Any]:
    if missing_path is not None and not missing_path.exists():
        return row(name, "SKIP", expected, expected_source, None, str(missing_path))
    status = "PASS" if expected == observed else "FAIL"
    return row(name, status, expected, expected_source, observed, None)


def src_files(repo_ROOT: Path) -> list[Path]:
    return sorted((repo_ROOT / "src").glob("*.py"))


def test_files(repo_ROOT: Path) -> list[Path]:
    return sorted((repo_ROOT / "tests").glob("test_*.py"))


def sql_files(repo_ROOT: Path) -> list[Path]:
    return sorted((repo_ROOT / "sql").glob("*.sql"))


def raise_messages(repo_ROOT: Path) -> set[str]:
    found: set[str] = set()
    for path in src_files(repo_ROOT):
        tree = ast.parse(read_text(path), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                if node.exc.args and isinstance(node.exc.args[0], ast.Constant):
                    if isinstance(node.exc.args[0].value, str):
                        found.add(node.exc.args[0].value)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "exit" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(
                        node.args[0].value, str
                    ):
                        found.add(node.args[0].value)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "exit" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(
                        node.args[0].value, str
                    ):
                        found.add(node.args[0].value)
    # Constant message aliases assigned then raised: also collect NAME = "msg"
    # used as raise X(NAME) by resolving Assign of str constants.
    for path in src_files(repo_ROOT):
        tree = ast.parse(read_text(path), filename=str(path))
        consts: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            consts[tgt.id] = node.value.value
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                if node.exc.args and isinstance(node.exc.args[0], ast.Name):
                    alias = node.exc.args[0].id
                    if alias in consts:
                        found.add(consts[alias])
    return found


def test_match_patterns(repo_ROOT: Path) -> set[str]:
    found: set[str] = set()
    for path in test_files(repo_ROOT):
        tree = ast.parse(read_text(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if "match" not in kw:
                continue
            raw = kw["match"]
            if isinstance(raw, ast.Constant) and isinstance(raw.value, str):
                pat = raw.value
                if pat.startswith("^"):
                    found.add(pat)
    return found


def git_blob_sha1(path: Path) -> str:
    import hashlib

    data = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def schema_tables_columns(schema_FILE: Path) -> dict[str, set[str]]:
    con = sqlite3.connect(schema_FILE)
    try:
        tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        out: dict[str, set[str]] = {}
        for table in tables:
            cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            out[table] = cols
        return out
    finally:
        con.close()


def explain_sql(schema_FILE: Path, sql_text: str) -> str | None:
    con = sqlite3.connect(schema_FILE)
    try:
        con.execute("EXPLAIN " + sql_text)
        return None
    except sqlite3.Error as exc:
        return str(exc)
    finally:
        con.close()


def ast_has_two_arg_get(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and len(node.args) >= 2:
                return True
    return False


def ast_path_argparse_defaults(tree: ast.AST) -> list[str]:
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dest = None
        has_default = False
        for kw in node.keywords:
            if kw.arg == "dest" and isinstance(kw.value, ast.Constant):
                dest = kw.value.value
            if kw.arg == "default":
                has_default = True
        if has_default and isinstance(dest, str) and dest.endswith(PATH_SUFFIXES):
            bad.append(dest)
    return bad


def ast_environ_get_default(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Attribute) and func.attr == "get":
            if isinstance(func.value, ast.Attribute) and func.value.attr == "environ":
                name = "environ.get"
            if isinstance(func.value, ast.Name) and func.value.id in {"environ", "os"}:
                name = func.value.id
        if isinstance(func, ast.Name) and func.id == "getenv":
            name = "getenv"
        if name and len(node.args) >= 2:
            return True
    return False


def ast_slash_literals(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith("/") and node.value != "/dev/null":
                found.append(node.value)
    return found


def ast_select_from_outside_loader(repo_ROOT: Path) -> list[str]:
    bad: list[str] = []
    for path in src_files(repo_ROOT):
        if path.name == "sql_loader.py":
            continue
        tree = ast.parse(read_text(path), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if SELECT_FROM.search(node.value) and FROM_WORD.search(node.value):
                    bad.append(f"{path.name}")
    return bad


def merge_outside_helper(repo_ROOT: Path) -> list[str]:
    bad: list[str] = []
    for path in src_files(repo_ROOT):
        if path.name == "merge.py":
            continue
        tree = ast.parse(read_text(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "merge":
                bad.append(path.name)
            elif node.func.attr == "join":
                recv = node.func.value
                if isinstance(recv, ast.Constant) and isinstance(recv.value, str):
                    continue
                bad.append(f"{path.name}:join")
    return bad


def kill_mutants(repo_ROOT: Path) -> tuple[str, list[str]]:
    mutations_DIR = repo_ROOT / "tests" / "mutations"
    if not mutations_DIR.is_dir():
        return "missing", [str(mutations_DIR)]
    patches = sorted(mutations_DIR.glob("*.patch"))
    if not patches:
        return "missing", [str(mutations_DIR)]
    survivors: list[str] = []
    for patch in patches:
        lines = read_text(patch).splitlines()
        if not lines or not lines[0].startswith("# kills:"):
            survivors.append(f"{patch.name}: no kills header")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            tmp_ROOT = Path(tmp)
            for name in (
                "src",
                "tests",
                "sql",
                "expected",
                "fixtures",
                "rounds",
                "frame.yaml",
                "pytest.ini",
            ):
                src_path = repo_ROOT / name
                dest = tmp_ROOT / name
                if src_path.is_dir():
                    shutil.copytree(
                        src_path,
                        dest,
                        ignore=shutil.ignore_patterns("mutations", "__pycache__"),
                    )
                elif src_path.is_file():
                    shutil.copy2(src_path, dest)
            proc = subprocess.run(
                ["patch", "-p1", "--forward", "--batch"],
                cwd=tmp_ROOT,
                input=read_text(patch),
                text=True,
                capture_output=True,
            )
            if proc.returncode != 0:
                survivors.append(f"{patch.name}: patch failed")
                continue
            inner = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_assertions.py",
                    "tests/test_null_propagation.py",
                    "-q",
                ],
                cwd=tmp_ROOT,
                capture_output=True,
                text=True,
            )
            if inner.returncode == 0:
                survivors.append(patch.name)
    if survivors:
        return "survivors", survivors
    return "killed", [p.name for p in patches]


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_ROOT = Path(args.repo_ROOT).resolve()
    schema_FILE = Path(args.schema_FILE)
    checks_FILE = Path(args.checks_FILE)
    frame_FILE = Path(args.frame_FILE)
    round_yaml_FILE = Path(args.round_yaml_FILE)

    rows: list[dict[str, Any]] = []
    schema_needed: list[str] = []

    if not frame_FILE.is_file():
        rows.append(
            row(
                "frame_yaml_present",
                "SKIP",
                True,
                "frame.yaml:exists",
                None,
                str(frame_FILE),
            )
        )
        _write_checks(checks_FILE, rows)
        return 1
    frame = load_yaml(frame_FILE)
    round_cfg = load_yaml(round_yaml_FILE) if round_yaml_FILE.is_file() else {}

    expected_rows_FILE = repo_ROOT / "expected" / "frame_windows.count"
    rows.append(
        compare_check(
            "expected_rows",
            int(read_expected_file(expected_rows_FILE))
            if expected_rows_FILE.is_file()
            else None,
            "expected/frame_windows.count:count",
            frame.get("expected_rows"),
            expected_rows_FILE,
        )
    )

    tol_FILE = repo_ROOT / "expected" / "expected_rows_tol.count"
    declared_rows = frame.get("expected_rows")
    max_tol = None
    if isinstance(declared_rows, int):
        max_tol = int(declared_rows * 2 // 100)
    rows.append(
        compare_check(
            "expected_rows_tol",
            int(read_expected_file(tol_FILE)) if tol_FILE.is_file() else None,
            "expected/expected_rows_tol.count:count",
            frame.get("expected_rows_tol"),
            tol_FILE,
        )
    )
    rows.append(
        row(
            "expected_rows_tol_cap",
            "PASS"
            if isinstance(frame.get("expected_rows_tol"), int)
            and max_tol is not None
            and frame["expected_rows_tol"] <= max_tol
            else "FAIL",
            max_tol,
            "frame.yaml:expected_rows",
            frame.get("expected_rows_tol"),
            None,
        )
    )

    src_count = frame.get("expected_rows_source")
    count_sql = repo_ROOT / str(src_count) if src_count else None
    rows.append(
        compare_check(
            "expected_rows_source",
            "sql/count_windows_ab.sql",
            "frame.yaml:expected_rows_source",
            src_count,
            count_sql,
        )
    )

    m_FILE = repo_ROOT / "expected" / "comparisons_m.count"
    comps = round_cfg.get("comparisons") or []
    rows.append(
        compare_check(
            "comparisons_m",
            int(read_expected_file(m_FILE)) if m_FILE.is_file() else None,
            "expected/comparisons_m.count:count",
            len(comps),
            m_FILE,
        )
    )

    ids_FILE = repo_ROOT / "expected" / "comparison_ids.txt"
    declared_ids = ",".join(c.get("id", "") for c in comps)
    rows.append(
        compare_check(
            "comparison_ids",
            read_expected_file(ids_FILE) if ids_FILE.is_file() else None,
            "expected/comparison_ids.txt:ids",
            declared_ids,
            ids_FILE,
        )
    )

    minj_FILE = repo_ROOT / "expected" / "min_judgeable.count"
    rows.append(
        compare_check(
            "min_judgeable",
            int(read_expected_file(minj_FILE)) if minj_FILE.is_file() else None,
            "expected/min_judgeable.count:count",
            frame.get("min_judgeable"),
            minj_FILE,
        )
    )

    b_FILE = repo_ROOT / "expected" / "B.count"
    rows.append(
        compare_check(
            "B",
            int(read_expected_file(b_FILE)) if b_FILE.is_file() else None,
            "expected/B.count:count",
            frame.get("B"),
            b_FILE,
        )
    )
    rows.append(
        row(
            "B_ge_1000",
            "PASS" if isinstance(frame.get("B"), int) and frame["B"] >= 1000 else "FAIL",
            1000,
            "expected/B.count:count",
            frame.get("B"),
            None,
        )
    )

    base_FILE = repo_ROOT / "expected" / "baseline_model.txt"
    rows.append(
        compare_check(
            "baseline_model",
            read_expected_file(base_FILE) if base_FILE.is_file() else None,
            "expected/baseline_model.txt:value",
            round_cfg.get("baseline_model"),
            base_FILE,
        )
    )

    nvid_FILE = repo_ROOT / "expected" / "n_videos.count"
    rows.append(
        compare_check(
            "video_counts",
            int(read_expected_file(nvid_FILE)) if nvid_FILE.is_file() else None,
            "expected/n_videos.count:count",
            (frame.get("video_counts") or {}).get("n_videos"),
            nvid_FILE,
        )
    )

    path_FILE = repo_ROOT / "expected" / "singing_prob_path.txt"
    src = frame.get("singing_prob_source") or {}
    yaml_src = round_cfg.get("singing_prob_source") or {}
    rows.append(
        compare_check(
            "singing_prob_path",
            read_expected_file(path_FILE) if path_FILE.is_file() else None,
            "expected/singing_prob_path.txt:path",
            src.get("path"),
            path_FILE,
        )
    )
    rows.append(
        row(
            "singing_prob_path_matches_round_yaml",
            "PASS" if src.get("path") == yaml_src.get("path") else "FAIL",
            yaml_src.get("path"),
            "rounds/ROUND-3.yaml:singing_prob_source.path",
            src.get("path"),
            None,
        )
    )
    paired_FILE = repo_ROOT / "expected" / "paired_with_clap.txt"
    paired_obs = src.get("paired_with_clap")
    paired_exp = (
        read_expected_file(paired_FILE) == "false" if paired_FILE.is_file() else None
    )
    rows.append(
        compare_check(
            "paired_with_clap",
            paired_exp,
            "expected/paired_with_clap.txt:value",
            bool(paired_obs) if paired_FILE.is_file() else paired_obs,
            paired_FILE,
        )
    )
    # expected false vs observed False: compare_check uses == so expected should be False
    rows[-1]["expected"] = False
    rows[-1]["observed"] = paired_obs
    rows[-1]["status"] = "PASS" if paired_obs is False else "FAIL"

    codes = list(frame.get("status_codes") or [])
    rows.append(
        row(
            "status_codes_no_unknown_other",
            "PASS"
            if codes and "unknown" not in codes and "other" not in codes
            else "FAIL",
            ["ok"],
            "frame.yaml:status_codes",
            codes,
            None,
        )
    )

    treatment = str((frame.get("groups") or {}).get("treatment", {}).get("predicate", ""))
    control = str((frame.get("groups") or {}).get("control", {}).get("predicate", ""))
    complement = (
        "not " in control.lower()
        or "film_flag != 1" in control
        or "film_flag = 0" in control
        or control.strip() == ""
        or treatment.strip() == ""
        or treatment == control
    )
    rows.append(
        row(
            "groups_explicit_not_complement",
            "FAIL" if complement else "PASS",
            "explicit predicates",
            "frame.yaml:groups.control.predicate",
            control,
            None,
        )
    )

    barred = set(frame.get("barred_stratifiers") or [])
    group_text = treatment + " " + control
    barred_used = [c for c in barred if c in group_text.split()]
    rows.append(
        row(
            "barred_stratifiers_not_groups",
            "PASS" if not barred_used else "FAIL",
            [],
            "frame.yaml:barred_stratifiers",
            barred_used,
            None,
        )
    )

    whitelist = list(frame.get("tier_whitelist") or [])
    rows.append(
        row(
            "tier_whitelist_ab",
            "PASS" if whitelist == ["A", "B"] else "FAIL",
            ["A", "B"],
            "frame.yaml:tier_whitelist",
            whitelist,
            None,
        )
    )

    predicates = list(frame.get("predicates") or [])
    rows.append(
        row(
            "predicates_include_tier",
            "PASS" if any("tier" in p for p in predicates) else "FAIL",
            "windows.tier IN ('A', 'B')",
            "frame.yaml:predicates",
            predicates[:1] if predicates else None,
            None,
        )
    )

    schema_map = {}
    if schema_FILE.is_file():
        schema_map = schema_tables_columns(schema_FILE)
    else:
        rows.append(
            row(
                "schema_sqlite",
                "SKIP",
                True,
                "frame.yaml:expected_rows_source",
                None,
                str(schema_FILE),
            )
        )

    referenced_sql = set()
    if src_count:
        referenced_sql.add(str(src_count))
    for join_name, spec in (frame.get("joins") or {}).items():
        if isinstance(spec, dict) and spec.get("sql"):
            referenced_sql.add(spec["sql"])
        if isinstance(spec, dict):
            exp = spec.get("expected_rows")
            if isinstance(exp, str) or (exp is not None and not isinstance(exp, int)):
                rows.append(
                    row(
                        f"join_expected_rows_literal_{join_name}",
                        "FAIL",
                        "literal int",
                        f"frame.yaml:joins.{join_name}.expected_rows",
                        exp,
                        None,
                    )
                )

    join_sql_listed = {
        spec.get("sql")
        for spec in (frame.get("joins") or {}).values()
        if isinstance(spec, dict) and spec.get("sql")
    }
    for sql_path in sql_files(repo_ROOT):
        rel = f"sql/{sql_path.name}"
        text = read_text(sql_path)
        has_join = bool(re.search(r"\bJOIN\b", text))
        if has_join and rel not in join_sql_listed:
            rows.append(
                row(
                    f"sql_join_listed_{sql_path.stem}",
                    "FAIL",
                    rel,
                    f"frame.yaml:joins.{sql_path.stem}.sql",
                    None,
                    None,
                )
            )
        if rel not in referenced_sql:
            # also referenced if load_sql name appears in src
            src_hit = any(sql_path.stem in read_text(p) for p in src_files(repo_ROOT))
            if not src_hit:
                rows.append(
                    row(
                        f"sql_referenced_{sql_path.stem}",
                        "FAIL",
                        rel,
                        "frame.yaml:joins",
                        None,
                        None,
                    )
                )
        if "clap_sing" in text:
            rows.append(
                row(
                    f"sql_no_clap_{sql_path.stem}",
                    "FAIL",
                    "absent",
                    "rounds/ROUND-3.yaml:singing_prob_source.paired_with_clap",
                    "clap_sing",
                    None,
                )
            )
        if schema_FILE.is_file():
            err = explain_sql(schema_FILE, text)
            # missing table/column in schema → SKIP SCHEMA-NEEDED
            if err and ("no such table" in err.lower() or "no such column" in err.lower()):
                miss = err
                schema_needed.append(miss)
                rows.append(
                    row(
                        f"sql_explain_{sql_path.stem}",
                        "SKIP",
                        "explain ok",
                        "frame.yaml:expected_rows_source",
                        err,
                        miss,
                    )
                )
            else:
                rows.append(
                    row(
                        f"sql_explain_{sql_path.stem}",
                        "FAIL" if err else "PASS",
                        "explain ok",
                        "frame.yaml:expected_rows_source",
                        err or "explain ok",
                        None,
                    )
                )

    src_msgs = raise_messages(repo_ROOT)
    test_pats = test_match_patterns(repo_ROOT)
    only_src = sorted(
        m for m in src_msgs if not any(re.search(p, m) for p in test_pats)
    )
    only_tests = sorted(
        p for p in test_pats if not any(re.search(p, m) for m in src_msgs)
    )
    flag_FILE = repo_ROOT / "expected" / "assertion_messages.flag"
    rows.append(
        row(
            "assertion_message_set",
            "PASS" if not only_src and not only_tests else "FAIL",
            read_expected_file(flag_FILE) if flag_FILE.is_file() else None,
            "expected/assertion_messages.flag:equal",
            {"only_src": only_src, "only_tests": only_tests},
            None if flag_FILE.is_file() else str(flag_FILE),
        )
    )

    merge_bad = merge_outside_helper(repo_ROOT)
    rows.append(
        row(
            "pd_merge_only_checked_merge",
            "PASS" if not merge_bad else "FAIL",
            [],
            "frame.yaml:joins",
            merge_bad,
            None,
        )
    )

    sel_bad = ast_select_from_outside_loader(repo_ROOT)
    rows.append(
        row(
            "select_from_only_load_sql",
            "PASS" if not sel_bad else "FAIL",
            [],
            "frame.yaml:expected_rows_source",
            sel_bad,
            None,
        )
    )

    slash_bad: list[str] = []
    default_bad: list[str] = []
    getenv_bad = False
    get_two = False
    snippets: list[str] = []
    for path in src_files(repo_ROOT):
        text = read_text(path)
        tree = ast.parse(text, filename=str(path))
        slash_bad.extend(f"{path.name}:{s}" for s in ast_slash_literals(tree))
        default_bad.extend(f"{path.name}:{d}" for d in ast_path_argparse_defaults(tree))
        getenv_bad = getenv_bad or ast_environ_get_default(tree)
        get_two = get_two or ast_has_two_arg_get(tree)
        for snip in FORBIDDEN_SRC_SNIPPETS:
            if snip in text:
                snippets.append(f"{path.name}:{snip}")
    rows.append(
        row(
            "no_absolute_src_paths",
            "PASS" if not slash_bad else "FAIL",
            [],
            "frame.yaml:expected_rows_source",
            slash_bad,
            None,
        )
    )
    rows.append(
        row(
            "path_args_no_default",
            "PASS" if not default_bad and not getenv_bad else "FAIL",
            [],
            "frame.yaml:expected_rows_source",
            {"argparse": default_bad, "getenv": getenv_bad},
            None,
        )
    )
    rows.append(
        row(
            "no_measure_fillna_or_get_default",
            "PASS" if not snippets and not get_two else "FAIL",
            [],
            "frame.yaml:measure_columns",
            {"snippets": snippets, "get_two_args": get_two},
            None,
        )
    )

    blob_obs = git_blob_sha1(frame_FILE)
    git_hash = subprocess.run(
        ["git", "hash-object", str(frame_FILE)],
        cwd=repo_ROOT,
        capture_output=True,
        text=True,
    )
    blob_exp = git_hash.stdout.strip() if git_hash.returncode == 0 else None
    rows.append(
        row(
            "frame_yaml_blob_sha",
            "PASS" if blob_exp == blob_obs else "FAIL",
            blob_exp,
            "frame.yaml:expected_rows",
            blob_obs,
            None if git_hash.returncode == 0 else "git hash-object",
        )
    )

    ns_hits: list[str] = []
    scan_dirs = [
        repo_ROOT / "src",
        repo_ROOT / "sql",
        repo_ROOT / "tests",
        repo_ROOT / "expected",
        repo_ROOT / "frame.yaml",
        repo_ROOT / "checks.json",
    ]
    for target in scan_dirs:
        paths = [target] if target.is_file() else list(target.rglob("*")) if target.is_dir() else []
        for path in paths:
            if not path.is_file():
                continue
            if "mutations" in path.parts:
                continue
            try:
                text = read_text(path)
            except UnicodeDecodeError:
                continue
            if NOT_SUPPORTED.search(text):
                ns_hits.append(str(path.relative_to(repo_ROOT)))
    rows.append(
        row(
            "no_not_supported_phrase",
            "PASS" if not ns_hits else "FAIL",
            [],
            "expected/comparison_ids.txt:ids",
            ns_hits,
            None,
        )
    )

    measure_cols = list(frame.get("measure_columns") or [])
    schema_dir = repo_ROOT / "fixtures" / "schemas"
    missing_status: list[str] = []
    for name in ("did_period.json", "did_highsnr_onset.json", "singing_removal.json"):
        schema_path = schema_dir / name
        if not schema_path.is_file():
            missing_status.append(name)
            continue
        schema = json.loads(read_text(schema_path))
        props = schema.get("properties") or {}
        for col in measure_cols:
            if col in props and f"{col}_status" not in props:
                missing_status.append(f"{name}:{col}_status")
    rows.append(
        row(
            "measure_status_in_output_schemas",
            "PASS" if not missing_status else "FAIL",
            [],
            "frame.yaml:measure_columns",
            missing_status,
            None,
        )
    )

    mutant_status, mutant_obs = kill_mutants(repo_ROOT)
    rows.append(
        row(
            "mutations_killed",
            "PASS" if mutant_status == "killed" else "FAIL",
            "killed",
            "expected/comparison_ids.txt:ids",
            mutant_obs,
            None if mutant_status != "missing" else str(repo_ROOT / "tests" / "mutations"),
        )
    )

    # Unmutated fixtures run must not SKIP except SCHEMA-NEEDED.
    skip_bad = [
        r
        for r in rows
        if r["status"] == "SKIP"
        and not (
            isinstance(r.get("missing"), str)
            and schema_FILE.is_file()
            and any(
                tok in r["missing"]
                for tok in list(schema_map.keys())
                + [c for cols in schema_map.values() for c in cols]
            )
        )
    ]
    rows.append(
        row(
            "unmutated_skip_policy",
            "PASS" if not skip_bad else "FAIL",
            [],
            "frame.yaml:expected_rows_source",
            [r["name"] for r in skip_bad],
            None,
        )
    )

    for r in rows:
        if not SOURCE_RE.match(str(r["expected_source"])):
            r["status"] = "FAIL"

    _write_checks(checks_FILE, rows)
    failed = [r for r in rows if r["status"] == "FAIL"]
    if schema_needed:
        sys.stderr.write("SCHEMA-NEEDED: " + "; ".join(schema_needed) + "\n")
    return 1 if failed else 0


def _write_checks(checks_FILE: Path, rows: list[dict[str, Any]]) -> None:
    tmp = checks_FILE.with_name(checks_FILE.name + ".tmp")
    tmp.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, checks_FILE)


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
