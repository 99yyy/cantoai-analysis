"""Each mutation patch applies and is killed by the named assertion."""

from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.hashing import verify_corpus_hash
from src.tables import open_corpus

ROOT = Path(__file__).resolve().parents[1]
MUT_DIR = ROOT / "tests" / "mutations"
CORPUS_PATH = ROOT / "data" / "corpus_v2.sqlite"
README_PATH = ROOT / "README.md"


def _header_message(patch_FILE: Path) -> str:
    first = patch_FILE.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("# kills: ")
    return first[len("# kills: ") :].strip()


def _apply(tmp_path: Path, patch_FILE: Path) -> Path:
    dest = tmp_path / "mutant"
    shutil.copytree(ROOT / "src", dest / "src")
    proc = subprocess.run(
        ["patch", "-p1", "--forward", "--batch", "-i", str(patch_FILE)],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stdout + proc.stderr)
    return dest


def _import(dest: Path, module: str):
    saved = {
        name: sys.modules[name]
        for name in list(sys.modules)
        if name == "src" or name.startswith("src.")
    }
    for name in saved:
        del sys.modules[name]
    sys.path.insert(0, str(dest))
    try:
        return importlib.import_module(module)
    finally:
        if str(dest) in sys.path:
            sys.path.remove(str(dest))
        sys.modules.update(saved)


def test_patches_apply_dry_run() -> None:
    for patch_FILE in sorted(MUT_DIR.glob("*.patch")):
        proc = subprocess.run(
            ["patch", "-p1", "--dry-run", "--forward", "--batch", "-i", str(patch_FILE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, patch_FILE.name + "\n" + proc.stdout + proc.stderr


def test_tier_filter_removed_killed(tmp_path: Path) -> None:
    patch_FILE = MUT_DIR / "tier_filter_removed.patch"
    msg = _header_message(patch_FILE)
    dest = _apply(tmp_path, patch_FILE)
    verify_corpus_hash(str(CORPUS_PATH), str(README_PATH))
    frame = _import(dest, "src.frame")
    conn = open_corpus(str(CORPUS_PATH))
    try:
        with pytest.raises(ValueError, match="^" + re.escape(msg)):
            frame.load_published_frame(conn)
    finally:
        conn.close()


def test_join_key_swapped_killed(tmp_path: Path) -> None:
    patch_FILE = MUT_DIR / "join_key_swapped.patch"
    msg = _header_message(patch_FILE)
    dest = _apply(tmp_path, patch_FILE)
    verify_corpus_hash(str(CORPUS_PATH), str(README_PATH))
    frame = _import(dest, "src.frame")
    conn = open_corpus(str(CORPUS_PATH))
    try:
        with pytest.raises(ValueError, match="^" + re.escape(msg)):
            frame.load_published_frame(conn)
    finally:
        conn.close()


def test_stratum_weights_ones_killed(tmp_path: Path) -> None:
    patch_FILE = MUT_DIR / "stratum_weights_ones.patch"
    msg = _header_message(patch_FILE)
    dest = _apply(tmp_path, patch_FILE)
    weights = _import(dest, "src.weights")
    N_h = np.array([10.0, 20.0])
    n_h = np.array([5.0, 8.0])
    w = weights.stratum_weights(N_h, n_h)
    with pytest.raises(ValueError, match="^" + re.escape(msg)):
        weights.assert_stratum_weights(w, N_h, n_h)


def test_stratum_seed_master_killed(tmp_path: Path) -> None:
    patch_FILE = MUT_DIR / "stratum_seed_master.patch"
    msg = _header_message(patch_FILE)
    dest = _apply(tmp_path, patch_FILE)
    bootstrap = _import(dest, "src.bootstrap")
    with pytest.raises(ValueError, match="^" + re.escape(msg)):
        bootstrap.make_stratum_seeds(20250918, ["film_pre", "film_post"])


def test_sentinel_ok_killed(tmp_path: Path) -> None:
    patch_FILE = MUT_DIR / "sentinel_ok.patch"
    msg = _header_message(patch_FILE)
    dest = _apply(tmp_path, patch_FILE)
    measures = _import(dest, "src.measures")
    df = pd.DataFrame({"n_judgeable": [0], "n_match": [0]})
    with pytest.raises(ValueError, match="^" + re.escape(msg)):
        measures.attach_agreement(df)
