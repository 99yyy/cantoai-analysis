"""Path-bearing names have no defaults. Atomic writes and STATUS.json loader."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

PATH_BEARING_NO_DEFAULT = "path-bearing argument has no default"
STATUS_NOT_COMPLETE = "STATUS.json is not complete or sha256 mismatch"
INFERENCE_BARRED = "inference entry points are barred this round"

_PATH_SUFFIXES = ("_PATH", "_DIR", "_FILE", "_ROOT")
_INFERENCE_MARKERS = (
    "run_clap",
    "run_window_quality",
    "run_demucs",
    "brouhaha",
    "dnsmos",
    "cnn14",
)


def require_path(name: str, value: str | None) -> Path:
    if not any(name.endswith(suffix) for suffix in _PATH_SUFFIXES):
        raise ValueError(PATH_BEARING_NO_DEFAULT)
    if value is None or value == "":
        raise ValueError(PATH_BEARING_NO_DEFAULT)
    return Path(value)


def environ_path(name: str) -> Path:
    value = os.environ.get(name)
    return require_path(name, value)


def refuse_inference(argv: list[str]) -> None:
    joined = " ".join(argv).lower()
    for marker in _INFERENCE_MARKERS:
        if marker in joined:
            raise ValueError(INFERENCE_BARRED)


def sha256_file(path_FILE: Path) -> str:
    digest = hashlib.sha256()
    with path_FILE.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_write_json(path_FILE: Path, obj: Any) -> str:
    payload = json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")
    digest = sha256_bytes(payload)
    tmp_FILE = path_FILE.with_name(path_FILE.name + ".tmp")
    tmp_FILE.write_bytes(payload)
    os.replace(tmp_FILE, path_FILE)
    return digest


def write_status(status_FILE: Path, status: str, sha256: str | None = None) -> None:
    body: dict[str, Any] = {"status": status}
    if sha256 is not None:
        body["sha256"] = sha256
    atomic_write_json(status_FILE, body)


def load_complete_output(path_FILE: Path, status_FILE: Path) -> bytes:
    if not status_FILE.is_file() or not path_FILE.is_file():
        raise ValueError(STATUS_NOT_COMPLETE)
    body = json.loads(status_FILE.read_text(encoding="utf-8"))
    if body.get("status") != "complete":
        raise ValueError(STATUS_NOT_COMPLETE)
    digest = sha256_file(path_FILE)
    recorded = body.get("sha256")
    if recorded != digest:
        raise ValueError(STATUS_NOT_COMPLETE)
    return path_FILE.read_bytes()
