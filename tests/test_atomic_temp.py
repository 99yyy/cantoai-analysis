from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from src.status_io import write_json_atomic, write_text_atomic

ROOT = Path(__file__).resolve().parents[1]


def test_two_writers_do_not_share_a_temp_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    names: list[str] = []
    parents: list[Path] = []
    real_replace = os.replace

    def spy(src, dst) -> None:
        source = Path(os.fspath(src))
        names.append(source.name)
        parents.append(source.parent)
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    dest = str(tmp_path / "out.json")
    write_json_atomic(dest, {"n": 1})
    write_text_atomic(dest, "second\n")
    assert names[0] != names[1]
    assert parents == [tmp_path, tmp_path]
    assert Path(dest).read_text(encoding="utf-8") == "second\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_concurrent_writers_leave_one_whole_payload(tmp_path: Path) -> None:
    dest = str(tmp_path / "out.json")
    pad = "粵" * 200

    def write(n: int) -> None:
        for i in range(20):
            write_json_atomic(dest, {"writer": n, "i": i, "pad": pad})

    threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    payload = json.loads(Path(dest).read_text(encoding="utf-8"))
    assert payload["pad"] == pad
    assert payload["writer"] in range(4)
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_atomic_keeps_non_ascii(tmp_path: Path) -> None:
    dest = str(tmp_path / "out.json")
    write_json_atomic(dest, {"word": "粵"})
    assert Path(dest).read_text(encoding="utf-8") == '{\n  "word": "粵"\n}\n'


def test_failed_replace_keeps_the_previous_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "out.json"
    write_json_atomic(str(dest), {"n": 1})

    def boom(src, dst) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_json_atomic(str(dest), {"n": 2})
    assert json.loads(dest.read_text(encoding="utf-8")) == {"n": 1}
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_follows_the_process_umask(tmp_path: Path) -> None:
    previous = os.umask(0o022)
    try:
        dest = tmp_path / "out.json"
        write_text_atomic(str(dest), "abc\n")
        assert dest.stat().st_mode & 0o777 == 0o644
    finally:
        os.umask(previous)


def test_src_does_not_build_a_shared_tmp_sibling() -> None:
    bad: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if '+ ".tmp"' in text or "+ '.tmp'" in text:
            bad.append(path.relative_to(ROOT).as_posix())
    assert bad == []
