#!/usr/bin/env python3
"""Detect a bar being lowered to make a check pass.

A "bar" is anything that decides whether a check passes: a declared expected
value, a tolerance, a threshold, a mutation patch, a counterexample pattern, or
a check in the contract checker itself. A "measured" file is anything a bar
judges: the analysis code, the SQL, the data.

Two rules, both mechanical:

1. One pull request may not change a bar and a measured file together. Lowering
   the bar in the same change that alters what it measures makes the check
   unfalsifiable, and the diff hides it. Measured paths are ``files − bar
   paths`` (plan §7 item 1 alternative): a gate script can be a counted bar
   without being measured against itself, so a legitimate dedupe with
   ``BAR-CHANGE:`` is not an automatic red.
2. A pull request that changes a bar at all must state why, as a line beginning
   ``BAR-CHANGE:`` in its body, naming each bar path it moves. A vague token is
   not a name. The line does not make the change right; it makes it visible to
   the round audit, which is where judgement belongs.

Counting rule for bars that are code: a NET REMOVAL is a bar change (fewer
checks emitted, fewer fail sites, fewer counterexample patterns, fewer
mutation patches). Adding checks is never flagged.

Dead detector paths are not deleted. They move into a ``RETIRED`` block
(plan §7 item 2 alternative) and new detectors sit alongside. The live∪RETIRED
glob inventory is a bar: dropping a token from both is a lowering; moving a
token from a live list into ``RETIRED`` is not.

Task briefs ``tasks/TASK-*.md`` declare bars in fenced ``numbers``, ``fixture``,
``frame``, ``n`` and ``identities`` blocks (plan §3.3). Widening a tolerance,
deleting a name (for ``identities``: deleting or rewording a line, or widening
its tolerance), or deleting a whole block is a bar move. Tightening a
tolerance is not.

The gate itself is a bar: any byte change to an existing file under
``scripts/`` or ``.github/``, or to a test file of a gate script
(``tests/test_<gate>*.py``, ``tests/mutations/``, ``tests/fixtures/``), is a
bar move. Such a change travels in its own pull request with a ``BAR-CHANGE:``
line naming the paths, and never together with measured paths.
Declared expected values in those blocks are bars under contract rule 6: any
change of the value, or deleting the name, is a bar move. Adding a name or a
block is not. The ``outside_frame`` block is the reverse: it lists names the
exclude invariant (relations.py) does not compare, so adding a name to it, or
adding the block, is a bar move; removing a name is not.

Usage:
  python scripts/history_audit.py --base origin/main --pr-body-file body.txt
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

# Adding a bar is normal: new code needs its expected value declared in the same
# change (contract clause 9). Only a bar that already existed and then moved, or
# disappeared, is a bar being lowered. Every rule below tests for that.
# Gate-script fail sites (Fail raises; appends on the fail list). output_check.py
# has dozens. scope_check.py has none of this token (it fails via
# ValueError / print FAIL); a rarer token must not freeze that file — rule 1
# already subtracts bar paths from measured (plan §7 item 1 alternative).
GATE_FAIL_SITE_RE = r"(?:raise Fail\(|fail\.append)"
# Live lists: globs this tree still uses. Dead paths are not deleted; they
# sit in RETIRED (plan §7 item 2 alternative). expected/ is empty here —
# declared bars live in task-brief fences (plan §3.3). gate_config.json holds
# the project facts every gate reads (tables, sides, number families); a change
# to it changes what the gates measure, so any edit is a bar move.
BAR_FILES: list[str] = [
    "scripts/gate_config.json",
    # The gate and the CI that runs it: any byte change is a bar move.
    "scripts/*", "scripts/**",
    ".github/*", ".github/**",
    # Tests of the gate scripts, their mutation probes and fixtures.
    "tests/test_output_check*.py", "tests/test_relations*.py",
    "tests/test_scope_check*.py", "tests/test_history_audit*.py",
    "tests/test_verify*.py", "tests/test_message_inventory*.py",
    "tests/test_mutations*.py", "tests/test_assertions*.py",
    "tests/mutations/*", "tests/mutations/**",
    "tests/fixtures/*", "tests/fixtures/**",
]
BAR_COUNTED = {
    "scripts/*.py": (GATE_FAIL_SITE_RE, "fail sites"),
    "scripts/**/*.py": (GATE_FAIL_SITE_RE, "fail sites"),
    "tests/*.py": (r"match\s*=", "counterexample patterns"),
    "tests/**/*.py": (r"match\s*=", "counterexample patterns"),
}
BAR_YAML_KEYS = re.compile(
    r"^\s*(expected_rows|expected_rows_tol|min_judgeable|B|threshold|max_concurrent|"
    r"launch_budget|baseline_model|expected_rows_source)\s*:", re.M
)
# Live YAML bar files. The old round-layout names are in RETIRED; fenced
# ``frame`` / ``fixture`` / ``n`` blocks replaced them (plan §3.3).
BAR_YAML_FILES: list[str] = []
MUTATION_GLOB = "tests/mutations/*.patch"

# sql/* and sql/** do not match tasks/TASK-N/sql/*.sql (fnmatch is
# prefix-anchored). Task analysis SQL lives there (plan §3.4). Kept live:
# a top-level sql/ path is still measured; absence of that directory is
# zero-cost, not a reason to retire the glob.
MEASURED = ["src/*", "src/**", "sql/*", "sql/**", "data/*", "data/**",
            "scripts/*.py", "scripts/**/*.py", "tasks/**/*.sql"]

# RETIRED-BEGIN
# Dead detector paths (plan §7 item 2 alternative). main() does not consult
# RETIRED. A detector that never fires while its path is absent is zero-cost;
# deleting it still violates strengthen-only. Move a glob here instead of
# removing it from the file. Restore by copying it back to the live list.
# Deleting a token from live AND from RETIRED shrinks detector_inventory and
# is a bar move. Adding a live glob alongside is not.
RETIRED = {
    "BAR_FILES": ["expected/*", "expected/**"],
    "BAR_COUNTED": {
        "scripts/contract_check.py": (
            r"\b(?:row|compare_check)\s*\(",
            "contract checks emitted",
        ),
    },
    "BAR_YAML_FILES": ["frame.yaml", "rounds/ROUND-*.yaml"],
}
RETIRED_LOGIC = r"""
# Original live fragments. Not executed. Restore by copying back into main()
# / the live lists. Kept so retirement is not deletion.
#
# BAR_FILES = ["expected/*", "expected/**"]
# for f in files:
#     if match_any(f, ["expected/*", "expected/**"]) and f in base_tree:
#         bars.append(f)
#
# BAR_COUNTED["scripts/contract_check.py"] = (
#     r"\b(?:row|compare_check)\s*\(", "contract checks emitted",
# )
#
# BAR_YAML_FILES = ["frame.yaml", "rounds/ROUND-*.yaml"]
# for f in files:
#     if match_any(f, ["frame.yaml", "rounds/ROUND-*.yaml"]):
#         bars.extend(yaml_bar_keys_touched(base, f))
"""
# RETIRED-END

RETIRED_BEGIN = "# RETIRED-BEGIN"
RETIRED_END = "# RETIRED-END"
HISTORY_AUDIT_PATH = "scripts/history_audit.py"
LIVE_INVENTORY_LISTS = frozenset({"BAR_FILES", "BAR_YAML_FILES", "MEASURED"})
LIVE_INVENTORY_DICTS = frozenset({"BAR_COUNTED"})
LIVE_INVENTORY_STRS = frozenset({"MUTATION_GLOB"})

# Top-level task briefs only. fnmatch '*' matches a slash, so tasks/TASK-*.md
# would also hit tasks/TASK-6/open_analysis.md.
TASK_BRIEF_RE = re.compile(r"^tasks/TASK-[^/]+\.md$")
DECL_KINDS = ("numbers", "fixture", "frame", "n", "identities")


def retired_block(text: str) -> str:
    """Inclusive slice between RETIRED markers. Empty if absent or inverted."""
    start = text.find(RETIRED_BEGIN)
    end = text.find(RETIRED_END)
    if start == -1 or end == -1 or end < start:
        return ""
    return text[start : end + len(RETIRED_END)]


def _list_strings(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out: list[str] = []
        for elt in node.elts:
            out.extend(_list_strings(elt))
        return out
    return []


def _dict_keys(node: ast.AST) -> list[str]:
    if not isinstance(node, ast.Dict):
        return []
    keys: list[str] = []
    for k in node.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.append(k.value)
    return keys


def _assignment_values(tree: ast.AST) -> list[tuple[str, ast.AST]]:
    out: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.append((t.id, node.value))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            out.append((node.target.id, node.value))
    return out


def _paths_from_retired_node(node: ast.AST) -> set[str]:
    """Glob tokens from a RETIRED = {...} dict (lists and BAR_COUNTED keys)."""
    paths: set[str] = set()
    if not isinstance(node, ast.Dict):
        return paths
    for k, v in zip(node.keys, node.values):
        cat = k.value if isinstance(k, ast.Constant) else None
        if cat == "BAR_COUNTED":
            paths.update(_dict_keys(v))
        elif cat in {"BAR_FILES", "BAR_YAML_FILES", "MEASURED"}:
            paths.update(_list_strings(v))
        elif cat == "MUTATION_GLOB":
            paths.update(_list_strings(v))
    return paths


def detector_inventory(text: str) -> frozenset[str]:
    """Path globs in live lists plus the RETIRED dict.

    Deleting a detector without keeping the glob in RETIRED shrinks this set.
    Retirement (live list → RETIRED) does not. Regex values and labels are
    not paths and are not counted.
    """
    if not text.strip():
        return frozenset()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return frozenset()
    paths: set[str] = set()
    for name, value in _assignment_values(tree):
        if name in LIVE_INVENTORY_LISTS:
            paths.update(_list_strings(value))
        elif name in LIVE_INVENTORY_DICTS:
            paths.update(_dict_keys(value))
        elif name in LIVE_INVENTORY_STRS:
            paths.update(_list_strings(value))
        elif name == "RETIRED":
            paths.update(_paths_from_retired_node(value))
    return frozenset(paths)


def live_detector_paths() -> frozenset[str]:
    """Globs the running check consults (imported constants, not source parse)."""
    paths = set(BAR_FILES) | set(BAR_COUNTED) | set(BAR_YAML_FILES) | set(MEASURED)
    paths.add(MUTATION_GLOB)
    return frozenset(paths)


def retired_detector_paths() -> frozenset[str]:
    """Globs preserved in RETIRED (imported constant, not source parse)."""
    paths: set[str] = set()
    for cat, val in RETIRED.items():
        if cat == "BAR_COUNTED" and isinstance(val, dict):
            paths.update(val)
        elif isinstance(val, (list, tuple)):
            paths.update(s for s in val if isinstance(s, str))
        elif isinstance(val, str):
            paths.add(val)
    return frozenset(paths)


DECL_FENCE = re.compile(
    r"^```(" + "|".join(DECL_KINDS) + r")\s*$(.*?)^```\s*$",
    re.M | re.S,
)
TOLERANCE_NAMES = frozenset({"tol", "tolerance"})
# Names exempt from relations.py's exclude invariant (one per line, no value).
EXEMPT_KIND = "outside_frame"
EXEMPT_FENCE = re.compile(r"^```outside_frame\s*$(.*?)^```\s*$", re.M | re.S)


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


def file_at(ref: str, path: str) -> str | None:
    try:
        return run("git", "show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return None


def _fmt_num(x: float) -> str:
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def _is_tolerance(kind: str, name: str) -> bool:
    if kind in ("numbers", "identities"):
        return True
    n = name.casefold()
    return n.endswith("_tol") or n in TOLERANCE_NAMES


def parse_decl_entries(body: str) -> dict[str, tuple[float, ...]]:
    """Name -> numeric fields on one declaration line.

    Comment-only and non-numeric lines (frame predicates) are skipped. A name
    that cannot be parsed is absent, so deleting it looks like a deletion.
    """
    out: dict[str, tuple[float, ...]] = {}
    for raw in body.splitlines():
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
        if not ok or not nums:
            continue
        name = parts[0]
        if name not in out:
            out[name] = tuple(nums)
    return out


def parse_identity_entries(body: str) -> dict[str, tuple[float, ...]]:
    """``<expr> = <expr>  <tol>`` lines keyed by the equation with whitespace
    collapsed; the value is the tolerance. Lines that do not parse are absent,
    so rewording an identity reads as deleting it."""
    out: dict[str, tuple[float, ...]] = {}
    for raw in body.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.rsplit(None, 1)
        if len(parts) != 2 or parts[0].count("=") != 1:
            continue
        try:
            tol = float(parts[1])
        except ValueError:
            continue
        key = " ".join(parts[0].split())
        if key not in out:
            out[key] = (tol,)
    return out


def parse_declaration_blocks(text: str) -> dict[str, dict[str, tuple[float, ...]]]:
    """First fenced block per kind. Later duplicates of the same kind are ignored."""
    blocks: dict[str, dict[str, tuple[float, ...]]] = {}
    for m in DECL_FENCE.finditer(text):
        kind = m.group(1)
        if kind in blocks:
            continue
        body = m.group(2)
        blocks[kind] = parse_identity_entries(body) if kind == "identities" else parse_decl_entries(body)
    return blocks


def parse_exempt_names(text: str) -> list[str]:
    """Names in the first ``outside_frame`` fence, in order; [] when there is none."""
    m = EXEMPT_FENCE.search(text)
    if not m:
        return []
    out: list[str] = []
    for raw in m.group(1).splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and line not in out:
            out.append(line.split()[0])
    return out


def exempt_bars(path: str, old_text: str, new_text: str) -> list[str]:
    """A name newly listed in ``outside_frame`` leaves the exclude invariant."""
    was = set(parse_exempt_names(old_text))
    now = parse_exempt_names(new_text)
    return [
        f"{path} ```{EXEMPT_KIND} {name} added (exempt from the exclude invariant)"
        for name in now
        if name not in was
    ]


def declaration_bars(path: str, old_text: str, new_text: str) -> list[str]:
    """Bar moves in fenced declaration blocks of a task brief (plan §3.3)."""
    old_blocks = parse_declaration_blocks(old_text)
    new_blocks = parse_declaration_blocks(new_text)
    hits: list[str] = exempt_bars(path, old_text, new_text)
    for kind in DECL_KINDS:
        was = old_blocks.get(kind)
        now = new_blocks.get(kind)
        if not was:
            continue
        if now is None:
            hits.append(f"{path} ```{kind} block deleted")
            continue
        for name, old_nums in was.items():
            new_nums = now.get(name)
            if new_nums is None:
                hits.append(f"{path} ```{kind} {name} deleted")
                continue
            if old_nums == new_nums:
                continue
            if _is_tolerance(kind, name) and len(old_nums) == 1 and len(new_nums) == 1:
                if new_nums[0] > old_nums[0]:
                    hits.append(
                        f"{path} ```{kind} {name} tolerance widened "
                        f"({_fmt_num(old_nums[0])} -> {_fmt_num(new_nums[0])})"
                    )
                continue
            hits.append(
                f"{path} ```{kind} {name} "
                f"({', '.join(_fmt_num(x) for x in old_nums)} -> "
                f"{', '.join(_fmt_num(x) for x in new_nums)})"
            )
    return sorted(hits)


def bar_path(bar: str) -> str:
    """The path a bar entry names (file, directory prefix, or yaml file)."""
    token = bar.split()[0]
    if ":" in token:
        token = token.split(":", 1)[0]
    return token


def measured_paths(files: list[str], bars: list[str]) -> list[str]:
    """Measured paths after subtracting bar paths (plan §7 item 1 alternative).

    ``scripts/*.py`` is in MEASURED and in BAR_COUNTED. Computing measured from
    the globs alone makes a net delete of fail sites both a bar and measured,
    so rule 1 is unconditionally red even with BAR-CHANGE. Subtract first.
    """
    barred = {bar_path(b) for b in bars}
    return sorted(f for f in files if match_any(f, MEASURED) and f not in barred)


def unnamed_bar_paths(bars: list[str], declared: list[str]) -> list[str]:
    """Bar paths that no ``BAR-CHANGE:`` line names.

    Matching is substring on the path with a trailing slash stripped, so
    ``tests/mutations/foo.patch`` names ``tests/mutations/``. A token such as
    ``x`` names nothing.
    """
    blob = "\n".join(declared)
    missing: list[str] = []
    seen: set[str] = set()
    for bar in bars:
        path = bar_path(bar)
        key = path.rstrip("/") or path
        if key in seen:
            continue
        seen.add(key)
        if key not in blob:
            missing.append(path)
    return missing


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

    for f in files:
        if not TASK_BRIEF_RE.match(f) or f not in base_tree:
            continue
        old = file_at(args.base, f) or ""
        new = file_at("HEAD", f) or ""
        bars.extend(declaration_bars(f, old, new))

    if HISTORY_AUDIT_PATH in files:
        was = detector_inventory(file_at(args.base, HISTORY_AUDIT_PATH) or "")
        now = detector_inventory(file_at("HEAD", HISTORY_AUDIT_PATH) or "")
        lost = sorted(was - now)
        if lost:
            bars.append(
                f"{HISTORY_AUDIT_PATH} (detector inventory {len(was)} -> {len(now)}; "
                f"lost {', '.join(lost)})"
            )

    bars = sorted(set(bars))
    measured = measured_paths(files, bars)

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
            unnamed = unnamed_bar_paths(bars, declared)
            if unnamed:
                print(
                    "history_audit: FAIL BAR-CHANGE does not name every bar path it moves: "
                    + ", ".join(unnamed)
                )
                failed = True

    if failed:
        return 1
    print("history_audit: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
