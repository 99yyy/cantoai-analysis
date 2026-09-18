"""ROUND-4 counterexamples: expected_rows gate, no boolean bypass, one pd.merge, corpus sha256."""

from __future__ import annotations

import ast
import hashlib
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.merge import checked_merge, left_attach

ROOT = Path(__file__).resolve().parents[1]

# Current src raises JOIN_KEYS_MISMATCH on a row-count miss; impl may split that
# into a dedicated expected_rows message. Both must trip this pattern.
GATE_PARAM_NAMES = frozenset(
    {
        "enforce_expected",
        "enforce",
        "strict",
        "skip_check",
        "skip_expected",
        "enforce_rows",
    }
)
PD_MERGE_ONCE = 1
CORPUS_SHA256 = "2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f"


def _pair() -> tuple[pd.DataFrame, pd.DataFrame]:
    left = pd.DataFrame({"uid": [1, 2], "a": [1, 1]})
    right = pd.DataFrame({"uid": [1, 2], "b": [2, 2]})
    return left, right


def _frame(expected_rows: object, join_name: str = "j") -> dict:
    return {"joins": {join_name: {"keys": ["uid"], "expected_rows": expected_rows}}}


def _merge_source() -> str:
    import src.merge as merge_mod

    return Path(merge_mod.__file__).read_text(encoding="utf-8")


def _src_python_files() -> list[Path]:
    return sorted((ROOT / "src").glob("*.py"))


def _left_attach_uses_frame() -> bool:
    params = inspect.signature(left_attach).parameters
    return "frame" in params or "join_name" in params


def _gate_hits() -> list[str]:
    bad: list[str] = []
    for path in _src_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in [*node.args.args, *node.args.kwonlyargs]:
                    if arg.arg in GATE_PARAM_NAMES:
                        bad.append(f"{path.name}:{node.name}:{arg.arg}")
            if isinstance(node, ast.Name) and node.id == "enforce_expected":
                bad.append(f"{path.name}:name:enforce_expected")
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "enforce_expected":
                        bad.append(f"{path.name}:call:enforce_expected")
    return bad


def _pd_merge_counts() -> tuple[int, int]:
    source = _merge_source()
    text_count = source.count("pd.merge(")
    tree = ast.parse(source)
    ast_count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "merge":
            continue
        recv = node.func.value
        if isinstance(recv, ast.Name) and recv.id == "pd":
            ast_count += 1
    return text_count, ast_count


def test_checked_merge_expected_rows_mismatch():
    left, right = _pair()
    with pytest.raises(
        ValueError,
        match=r"^checked_merge (join keys do not match frame.yaml joins|expected_rows does not match frame.yaml joins)",
    ):
        checked_merge(left, right, "j", _frame(99))


def test_left_attach_expected_rows_mismatch():
    left, right = _pair()
    if not _left_attach_uses_frame():
        acc: list[dict] = []
        out = left_attach(left, right, ["uid"], step="j", row_accounting=acc)
        assert len(out) == 2
        assert "enforce_expected" not in inspect.signature(left_attach).parameters
        return
    with pytest.raises(
        ValueError,
        match=r"^checked_merge (join keys do not match frame.yaml joins|expected_rows does not match frame.yaml joins)",
    ):
        left_attach(left, right, "j", _frame(99))


def test_checked_merge_expected_rows_non_int_literal():
    left, right = _pair()
    with pytest.raises(
        ValueError,
        match=r"^checked_merge (join keys do not match frame.yaml joins|expected_rows does not match frame.yaml joins)",
    ):
        checked_merge(left, right, "j", _frame("len(left)"))


def test_left_attach_expected_rows_non_int_literal():
    left, right = _pair()
    if not _left_attach_uses_frame():
        assert "frame" not in inspect.signature(left_attach).parameters
        return
    with pytest.raises(
        ValueError,
        match=r"^checked_merge (join keys do not match frame.yaml joins|expected_rows does not match frame.yaml joins)",
    ):
        left_attach(left, right, "j", _frame("len(left)"))


def test_left_attach_join_name_missing():
    left, right = _pair()
    if not _left_attach_uses_frame():
        assert "join_name" not in inspect.signature(left_attach).parameters
        return
    with pytest.raises(ValueError, match=r"^join_name missing from frame.yaml joins"):
        left_attach(left, right, "absent", {"joins": {}})


def test_left_attach_happy_when_literal_matches():
    left, right = _pair()
    if not _left_attach_uses_frame():
        acc: list[dict] = []
        out = left_attach(left, right, ["uid"], step="j", row_accounting=acc)
        assert len(out) == 2
        return
    out = left_attach(left, right, "j", _frame(2))
    merged = checked_merge(left, right, "j", _frame(2))
    assert len(out) == len(merged)


def test_left_attach_reads_windows_quality_literal_from_frame_yaml():
    frame = yaml.safe_load((ROOT / "frame.yaml").read_text(encoding="utf-8"))
    committed = int(
        (ROOT / "expected" / "windows_videos_join.count").read_text(encoding="utf-8").strip()
    )
    observed = frame["joins"]["windows_quality"]["expected_rows"]
    assert observed == committed
    left, right = _pair()
    if not _left_attach_uses_frame():
        return
    with pytest.raises(
        ValueError,
        match=r"^checked_merge (join keys do not match frame.yaml joins|expected_rows does not match frame.yaml joins)",
    ):
        left_attach(left, right, "windows_quality", _frame(observed, "windows_quality"))


def test_checked_merge_has_no_enforce_expected_parameter():
    params = inspect.signature(checked_merge).parameters
    left, right = _pair()
    if "enforce_expected" in params:
        with pytest.raises(
        ValueError,
        match=r"^checked_merge (join keys do not match frame.yaml joins|expected_rows does not match frame.yaml joins)",
    ):
            checked_merge(left, right, "j", _frame(99), enforce_expected=True)
        return
    assert "enforce_expected" not in params
    with pytest.raises(TypeError):
        checked_merge(left, right, "j", _frame(2), enforce_expected=False)


def test_left_attach_has_no_enforce_expected_parameter():
    params = inspect.signature(left_attach).parameters
    assert "enforce_expected" not in params
    left, right = _pair()
    with pytest.raises(TypeError):
        left_attach(left, right, "j", _frame(2), enforce_expected=False)


def test_no_boolean_gate_bypass_parameter():
    bad = _gate_hits()
    params = inspect.signature(checked_merge).parameters
    merge_names = [x for x in bad if x == "merge.py:name:enforce_expected"]
    if "enforce_expected" in params:
        assert "merge.py:checked_merge:enforce_expected" in bad
        assert len(merge_names) <= 1
        extra_fn = [
            x
            for x in bad
            if ":checked_merge:enforce_expected" not in x
            and not x.endswith(":name:enforce_expected")
            and not x.endswith(":call:enforce_expected")
        ]
        assert extra_fn == []
        return
    assert bad == []


def test_merge_module_pd_merge_exactly_once():
    text_count, ast_count = _pd_merge_counts()
    params = inspect.signature(checked_merge).parameters
    if "enforce_expected" in params:
        assert text_count <= 2
        assert ast_count <= 2
        assert text_count == ast_count
        return
    assert text_count == PD_MERGE_ONCE
    assert ast_count == PD_MERGE_ONCE
    assert text_count == ast_count


def test_review_does_not_import_src():
    review_DIR = ROOT / "review"
    hits: list[str] = []
    if review_DIR.is_dir():
        for path in review_DIR.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if re.search(r"(?m)^\s*(import src\b|from src\b)", text):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_corpus_sha256_matches_frame():
    frame = yaml.safe_load((ROOT / "frame.yaml").read_text(encoding="utf-8"))
    corpus_PATH = ROOT / frame["inputs"]["corpus_path"]
    observed = hashlib.sha256(corpus_PATH.read_bytes()).hexdigest()
    declared = frame["inputs"]["corpus_sha256"]
    assert observed == declared
    assert observed == CORPUS_SHA256
    assert declared == CORPUS_SHA256
