#!/usr/bin/env python3
"""Re-pin the corpus: rewrite the pin file's sha256 to the corpus on disk.

Owner-only (``repair/``). Run after the new corpus file is in place at the
path ``gate_config.json`` names:

    python scripts/repin.py            # rewrite the pin, report what goes STALE
    python scripts/repin.py --check    # report only, change nothing

What it touches: the one ``sha256:`` line of the pin file. Nothing else.
Closed briefs keep their ``corpus_sha:`` stamp and become STALE (output-check
skips them, they do not fail); their RESULT.json keeps the stamp it was
computed under, which is what output-check now expects. To bring a task back
onto the new corpus, reopen it (``status: open``) and run the loop again; do
not edit a closed task's files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PIN_RE = re.compile(r"sha256:\s*`?([0-9a-f]{64})`?")
STAMP_RE = re.compile(r"^corpus_sha:[ \t]*`?([0-9a-f]{64})`?[ \t]*$", re.M)
STATUS_RE = re.compile(r"^status:[ \t]*(open|closed|escalated|blocked)[ \t]*$", re.M)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(ROOT))
    ap.add_argument("--check", action="store_true", help="report only; do not rewrite the pin")
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()
    cfg = json.loads((HERE / "gate_config.json").read_text(encoding="utf-8"))
    corpus = root / cfg["corpus"]
    pin_file = root / cfg["pin_file"]
    if not corpus.is_file():
        print(f"repin: {cfg['corpus']} does not exist")
        return 1
    text = pin_file.read_text(encoding="utf-8")
    m = PIN_RE.search(text)
    if not m:
        print(f"repin: {cfg['pin_file']} has no sha256: line")
        return 1
    old, new = m.group(1), sha256_file(corpus)
    print(f"repin: pin {old[:16]}… -> {new[:16]}…" if old != new else f"repin: pin already {new[:16]}…")

    stale: list[str] = []
    for md in sorted((root / "tasks").glob("TASK-*.md")):
        body = md.read_text(encoding="utf-8")
        st = STATUS_RE.findall(body)
        if st != ["closed"]:
            continue
        stamp = STAMP_RE.search(body)
        if stamp is None or stamp.group(1) != new:
            stale.append(md.name)
    if stale:
        print("repin: closed briefs STALE under the new pin (skipped by output-check, not red):")
        for name in stale:
            print(f"  {name}")
    else:
        print("repin: no closed brief goes STALE")

    if args.check or old == new:
        return 0
    pin_file.write_text(text[: m.start(1)] + new + text[m.end(1):], encoding="utf-8")
    print(f"repin: wrote {cfg['pin_file']}; commit it with the corpus on a repair/ branch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
