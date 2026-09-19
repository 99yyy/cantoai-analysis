"""Probe: src/**/*.py must not contain README/frame table-size integer literals."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from src.hashing import verify_corpus_hash
from src.pins import load_frame_counts, parse_readme_table_sizes

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
README_PATH = ROOT / "README.md"
BRIEF_PATH = ROOT / "tasks" / "TASK-6.md"
CORPUS_PATH = ROOT / "data" / "corpus_v2.sqlite"


def forbidden_pin_ints(readme_PATH: str, brief_PATH: str) -> set[int]:
    """README videos/windows/syllables sizes, plus frame published_expected.

    ``runs`` is recorded as 1 in README; that token is not a table size we can
    scan for. published_expected is the A+B fence, which README does not pin.
    """
    sizes = parse_readme_table_sizes(readme_PATH)
    pins = {sizes["videos"], sizes["windows"], sizes["syllables"]}
    pins.add(load_frame_counts(brief_PATH, readme_PATH).published_expected)
    return pins


def pin_literals_in_src(src_DIR: Path, pins: set[int]) -> list[str]:
    """Return hit strings for integer tokens in *pins* anywhere under src_DIR."""
    hits: list[str] = []
    token = re.compile(
        r"\b(" + "|".join(str(n) for n in sorted(pins)) + r")\b"
    )
    for path in sorted(src_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        rel = path.as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in token.finditer(line):
                hits.append(f"{rel}:{lineno}:{match.group(1)}")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            value = node.value
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and value in pins:
                loc = f"{rel}:{getattr(node, 'lineno', 0)}:{value}"
                if loc not in hits:
                    hits.append(loc)
            if isinstance(value, float) and int(value) == value and int(value) in pins:
                loc = f"{rel}:{getattr(node, 'lineno', 0)}:{int(value)}"
                if loc not in hits:
                    hits.append(loc)
    return hits


def test_src_has_no_readme_or_frame_pin_integer_literals() -> None:
    verify_corpus_hash(str(CORPUS_PATH), str(README_PATH))
    pins = forbidden_pin_ints(str(README_PATH), str(BRIEF_PATH))
    hits = pin_literals_in_src(SRC_ROOT, pins)
    assert hits == [], hits


def test_pin_literal_probe_goes_red_on_injected_readme_table_size(tmp_path: Path) -> None:
    """Must-go-red: a src module that hardcodes a README table size fails the scan."""
    verify_corpus_hash(str(CORPUS_PATH), str(README_PATH))
    pins = forbidden_pin_ints(str(README_PATH), str(BRIEF_PATH))
    videos_n = parse_readme_table_sizes(str(README_PATH))["videos"]
    src_DIR = tmp_path / "src"
    src_DIR.mkdir()
    (src_DIR / "hardcoded.py").write_text(
        "VIDEOS_N = {n}\n".format(n=videos_n),
        encoding="utf-8",
    )
    hits = pin_literals_in_src(src_DIR, pins)
    assert hits, "probe stayed green on an injected README table-size literal"
    assert any(str(videos_n) in h for h in hits)
