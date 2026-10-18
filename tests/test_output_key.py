from __future__ import annotations

from pathlib import Path

import pytest

from src.status_io import (
    output_entries,
    output_key,
    read_completed_output,
    sha256_file,
    write_status,
)


def test_same_filename_keeps_its_own_hash(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    first = tmp_path / "a" / "out.json"
    second = tmp_path / "b" / "out.json"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"one\n")
    second.write_bytes(b"two\n")
    write_status(
        status_FILE,
        {
            "status": "complete",
            "outputs": output_entries(status_FILE, [str(first), str(second)]),
        },
    )
    assert output_key(status_FILE, str(first)) == "a/out.json"
    assert output_key(status_FILE, str(second)) == "b/out.json"
    assert read_completed_output(status_FILE, str(first)) == b"one\n"
    assert read_completed_output(status_FILE, str(second)) == b"two\n"


def test_basename_key_still_reads_the_sibling(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    Path(out_FILE).write_bytes(b"one\n")
    write_status(
        status_FILE,
        {"status": "complete", "outputs": {"out.json": sha256_file(out_FILE)}},
    )
    assert output_key(status_FILE, out_FILE) == "out.json"
    assert read_completed_output(status_FILE, out_FILE) == b"one\n"


def test_basename_fallback_reads_a_nested_file(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "a" / "out.json")
    Path(out_FILE).parent.mkdir()
    Path(out_FILE).write_bytes(b"one\n")
    write_status(
        status_FILE,
        {"status": "complete", "outputs": {"out.json": sha256_file(out_FILE)}},
    )
    assert read_completed_output(status_FILE, out_FILE) == b"one\n"


def test_other_qualified_key_does_not_satisfy_a_third_path(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    first = tmp_path / "a" / "out.json"
    second = tmp_path / "b" / "out.json"
    third = tmp_path / "c" / "out.json"
    for path in (first, second, third):
        path.parent.mkdir()
        path.write_bytes(b"one\n")
    write_status(
        status_FILE,
        {
            "status": "complete",
            "outputs": output_entries(status_FILE, [str(first), str(second)]),
        },
    )
    with pytest.raises(ValueError, match=r"^STATUS\.json output name is ambiguous"):
        read_completed_output(status_FILE, str(third))


def test_output_entries_rejects_one_file_twice(tmp_path: Path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    Path(out_FILE).write_bytes(b"one\n")
    with pytest.raises(ValueError, match=r"^STATUS\.json output name is ambiguous"):
        output_entries(status_FILE, [out_FILE, out_FILE])


def test_output_key_outside_the_status_dir_is_absolute(tmp_path: Path) -> None:
    status_dir = tmp_path / "run"
    status_dir.mkdir()
    status_FILE = str(status_dir / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    Path(out_FILE).write_bytes(b"one\n")
    assert output_key(status_FILE, out_FILE) == Path(out_FILE).resolve().as_posix()
    write_status(
        status_FILE,
        {
            "status": "complete",
            "outputs": output_entries(status_FILE, [out_FILE]),
        },
    )
    assert read_completed_output(status_FILE, out_FILE) == b"one\n"
