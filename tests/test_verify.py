"""./verify wraps CI scripts; probe must go red; TASK-6 smoke on this checkout."""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "verify"
SPEC = importlib.util.spec_from_file_location(
    "verify_script", ROOT / "scripts" / "verify.py"
)
assert SPEC is not None and SPEC.loader is not None
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def test_verify_wrapper_is_executable():
    mode = VERIFY.stat().st_mode
    assert VERIFY.is_file()
    assert mode & stat.S_IXUSR


def test_parse_argv_fixed_commands():
    assert verify.parse_argv([]) == ("full", None)
    assert verify.parse_argv(["probe"]) == ("probe", None)
    assert verify.parse_argv(["task", "6"]) == ("task", "6")
    assert verify.parse_argv(["relations", "6"]) == ("relations", "6")


def test_unknown_subcommand_exits_2():
    proc = subprocess.run(
        [str(VERIFY), "nope"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    combined = proc.stdout + proc.stderr
    assert "./verify task" in combined
    assert "./verify probe" in combined


def test_probe_exits_zero_because_known_red_probes_go_red():
    proc = subprocess.run(
        [str(VERIFY), "probe"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "probe constant-sql went red" in out
    assert "probe relations-literal-denom went red" in out
    assert "probe result-out-of-turns went red" in out
    assert "verify: probe PASS" in out


@pytest.mark.skipif(
    os.environ.get("VERIFY_RUNNING") == "1",
    reason="outer ./verify already runs the suite",
)
def test_verify_task_6_exits_zero_on_this_checkout():
    proc = subprocess.run(
        [str(VERIFY), "task", "6"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "only TASK-6" in out
    assert "output_check: PASS" in out
    assert "relations: PASS" in out
    assert "verify: PASS" in out
