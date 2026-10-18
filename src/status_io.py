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


def _output_hashes(output_FILES: list[str]) -> dict[str, str]:
    if len(output_FILES) == 0:
        raise ValueError("STATUS.json publish list is empty")
    names = [Path(path_FILE).name for path_FILE in output_FILES]
    if len(set(names)) != len(names):
        raise ValueError("STATUS.json output names collide")
    outputs: dict[str, str] = {}
    for path_FILE in output_FILES:
        if not Path(path_FILE).is_file():
            raise ValueError("STATUS.json output file is missing")
        outputs[Path(path_FILE).name] = sha256_file(path_FILE)
    return outputs


def publish_outputs(status_FILE: str, output_FILES: list[str]) -> dict[str, str]:
    outputs = _output_hashes(output_FILES)
    path = Path(status_FILE)
    if not path.is_file():
        raise ValueError("STATUS.json is not running")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") == "complete":
        if payload.get("outputs") == outputs:
            return outputs
        raise ValueError("STATUS.json is already complete")
    if payload.get("status") != "running":
        raise ValueError("STATUS.json is not running")
    write_status(status_FILE, {"status": "complete", "outputs": outputs})
    return outputs


def read_completed_output(status_FILE: str, out_FILE: str) -> bytes:
    payload = json.loads(Path(status_FILE).read_text(encoding="utf-8"))
    if payload.get("status") != "complete":
        raise ValueError("STATUS.json is not complete")
    outputs = payload.get("outputs") or {}
    name = Path(out_FILE).name
    expected = outputs.get(name)
    got = sha256_file(out_FILE)
    if expected != got:
        print(got, expected)
        raise ValueError("STATUS.json sha256 does not match output")
    return Path(out_FILE).read_bytes()
