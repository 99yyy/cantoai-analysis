"""The set of src assertion messages equals the set of ^-anchored pytest match patterns."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
TEST_ROOT = ROOT / "tests"
MATCH_RE = re.compile(r"match\s*=\s*r([\"'])\^(.+?)\1")


def src_messages() -> set[str]:
    found: set[str] = set()
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            if not node.exc.args:
                continue
            arg0 = node.exc.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                found.add(arg0.value)
            if isinstance(node.exc.func, ast.Name) and node.exc.func.id == "SystemExit":
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    found.add(arg0.value)
    return found


def match_patterns() -> list[str]:
    patterns: list[str] = []
    for path in sorted(TEST_ROOT.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        for match in MATCH_RE.finditer(text):
            patterns.append(match.group(2))
    return patterns


def test_assertion_message_sets_are_equal() -> None:
    src = src_messages()
    patterns = match_patterns()
    matched: set[str] = set()
    unused: list[str] = []
    for pat in patterns:
        regex = re.compile("^" + pat)
        hits = [msg for msg in src if regex.match(msg)]
        if not hits:
            unused.append(pat)
        matched.update(hits)
    missing = sorted(src - matched)
    extra = unused
    assert missing == [] and extra == [], (
        "src messages missing a test match: "
        f"{missing}; test patterns with no src message: {extra}; "
        f"src={sorted(src)}; patterns={patterns}"
    )
    assert len(src) == len(set(patterns))
