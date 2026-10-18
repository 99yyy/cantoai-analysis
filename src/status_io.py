from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path_FILE: str) -> str:
    digest = hashlib.sha256()
    with open(path_FILE, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path_FILE: str, payload: object) -> None:
    target = Path(path_FILE)
    tmp_FILE = str(target) + ".tmp"
    Path(tmp_FILE).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    Path(tmp_FILE).replace(target)


def write_text_atomic(path_FILE: str, text: str) -> None:
    target = Path(path_FILE)
    tmp_FILE = str(target) + ".tmp"
    Path(tmp_FILE).write_text(text, encoding="utf-8")
    Path(tmp_FILE).replace(target)


def write_status(status_FILE: str, payload: dict) -> None:
    write_json_atomic(status_FILE, payload)


def output_key(status_FILE: str, out_FILE: str) -> str:
    status_dir = Path(status_FILE).resolve().parent
    target = Path(out_FILE).resolve()
    try:
        relative = target.relative_to(status_dir)
    except ValueError:
        return target.as_posix()
    return relative.as_posix()


def output_entries(status_FILE: str, output_FILES: list[str]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for out_FILE in output_FILES:
        key = output_key(status_FILE, out_FILE)
        if key in entries:
            raise ValueError("STATUS.json output name is ambiguous")
        entries[key] = sha256_file(out_FILE)
    return entries


def _expected_hash(outputs: dict, status_FILE: str, out_FILE: str):
    qualified = output_key(status_FILE, out_FILE)
    if qualified in outputs:
        return outputs[qualified]
    base = Path(out_FILE).name
    same = [key for key in outputs if Path(str(key)).name == base]
    if same == [base]:
        return outputs[base]
    if same:
        raise ValueError("STATUS.json output name is ambiguous")
    return None


def read_completed_output(status_FILE: str, out_FILE: str) -> bytes:
    payload = json.loads(Path(status_FILE).read_text(encoding="utf-8"))
    if payload.get("status") != "complete":
        raise ValueError("STATUS.json is not complete")
    outputs = payload.get("outputs") or {}
    expected = _expected_hash(outputs, status_FILE, out_FILE)
    got = sha256_file(out_FILE)
    if expected != got:
        print(got, expected)
        raise ValueError("STATUS.json sha256 does not match output")
    return Path(out_FILE).read_bytes()
