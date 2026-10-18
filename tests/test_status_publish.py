from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.status_io import (
    publish_outputs,
    read_completed_output,
    sha256_file,
    write_status,
)

ROOT = Path(__file__).resolve().parents[1]
COMPLETE_LITERAL = re.compile(r"""['\"]complete['\"]""")


def test_publish_outputs_records_the_file_bytes(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    write_status(status_FILE, {"status": "running"})
    Path(out_FILE).write_bytes(b"abc\n")
    outputs = publish_outputs(status_FILE, [out_FILE])
    assert outputs == {"out.json": sha256_file(out_FILE)}
    assert read_completed_output(status_FILE, out_FILE) == b"abc\n"
    assert publish_outputs(status_FILE, [out_FILE]) == outputs
    assert read_completed_output(status_FILE, out_FILE) == b"abc\n"


def test_publish_outputs_refuses_a_changed_file_after_complete(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    write_status(status_FILE, {"status": "running"})
    Path(out_FILE).write_bytes(b"abc\n")
    publish_outputs(status_FILE, [out_FILE])
    Path(out_FILE).write_bytes(b"zzz\n")
    with pytest.raises(ValueError, match=r"^STATUS\.json is already complete"):
        publish_outputs(status_FILE, [out_FILE])
    with pytest.raises(ValueError, match=r"^STATUS\.json sha256 does not match output"):
        read_completed_output(status_FILE, out_FILE)


def test_publish_outputs_requires_running(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    Path(out_FILE).write_bytes(b"abc\n")
    with pytest.raises(ValueError, match=r"^STATUS\.json is not running"):
        publish_outputs(status_FILE, [out_FILE])
    write_status(status_FILE, {"status": "other"})
    with pytest.raises(ValueError, match=r"^STATUS\.json is not running"):
        publish_outputs(status_FILE, [out_FILE])


def test_publish_outputs_rejects_an_empty_list(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    write_status(status_FILE, {"status": "running"})
    with pytest.raises(ValueError, match=r"^STATUS\.json publish list is empty"):
        publish_outputs(status_FILE, [])


def test_publish_outputs_rejects_colliding_names(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    write_status(status_FILE, {"status": "running"})
    first = tmp_path / "a" / "out.json"
    second = tmp_path / "b" / "out.json"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"one\n")
    second.write_bytes(b"two\n")
    with pytest.raises(ValueError, match=r"^STATUS\.json output names collide"):
        publish_outputs(status_FILE, [str(first), str(second)])
    assert json.loads(Path(status_FILE).read_text(encoding="utf-8"))["status"] == "running"


def test_publish_outputs_rejects_a_missing_file(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    write_status(status_FILE, {"status": "running"})
    missing_FILE = str(tmp_path / "gone.json")
    with pytest.raises(ValueError, match=r"^STATUS\.json output file is missing"):
        publish_outputs(status_FILE, [missing_FILE])
    assert json.loads(Path(status_FILE).read_text(encoding="utf-8"))["status"] == "running"


def test_src_complete_literal_lives_only_in_status_io() -> None:
    bad: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if path.name == "status_io.py":
            continue
        if COMPLETE_LITERAL.search(path.read_text(encoding="utf-8")):
            bad.append(path.relative_to(ROOT).as_posix())
    assert bad == []
