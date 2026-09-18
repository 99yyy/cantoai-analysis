"""Pin the corpus file against the hash recorded in README.md."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_README_SHA = re.compile(r"sha256:\s*`?([0-9a-f]{64})`?")


def corpus_sha256(corpus_PATH: str) -> str:
    digest = hashlib.sha256()
    with open(corpus_PATH, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def readme_sha256(readme_PATH: str) -> str:
    text = Path(readme_PATH).read_text(encoding="utf-8")
    match = _README_SHA.search(text)
    if match is None:
        raise ValueError("README.md records no sha256 for the corpus")
    return match.group(1)


def verify_corpus_hash(corpus_PATH: str, readme_PATH: str) -> str:
    got = corpus_sha256(corpus_PATH)
    want = readme_sha256(readme_PATH)
    if got != want:
        print(got, want)
        raise ValueError("corpus sha256 does not match README.md")
    return got
