"""Manifest construction (schema-shaped; values supplied by the caller)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

GIT_DIRTY_REJECTED = "git_dirty true is rejected"
UPLOAD_DATE_MISSING = "upload_date missing"


def git_blob_sha1(path_FILE: Path) -> str:
    data = path_FILE.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def assert_git_clean(git_dirty: bool) -> None:
    if git_dirty:
        raise ValueError(GIT_DIRTY_REJECTED)


def parse_upload_date(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        raise ValueError(UPLOAD_DATE_MISSING)
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    raise ValueError(UPLOAD_DATE_MISSING)


def build_manifest(
    *,
    inputs: list[dict[str, Any]],
    strata: list[dict[str, Any]],
    master_seed: int,
    stratum_seeds: dict[str, int],
    B: int,
    git_sha: str,
    git_dirty: bool,
    frame_yaml_blob_sha: str,
    row_accounting: list[dict[str, Any]],
    unassigned: int,
) -> dict[str, Any]:
    assert_git_clean(git_dirty)
    return {
        "inputs": inputs,
        "strata": strata,
        "master_seed": master_seed,
        "stratum_seeds": stratum_seeds,
        "B": B,
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "frame_yaml_blob_sha": frame_yaml_blob_sha,
        "row_accounting": row_accounting,
        "unassigned": unassigned,
    }
