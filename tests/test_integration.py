"""Load the pinned corpus through the published-set frame."""

from __future__ import annotations

from pathlib import Path

from src.agreement import agreement_counts
from src.frame import load_published_frame
from src.groups import assign_groups
from src.hashing import verify_corpus_hash
from src.pins import load_frame_counts
from src.status_io import read_completed_output, sha256_file, write_status
from src.tables import open_corpus

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "data" / "corpus_v2.sqlite"
README_PATH = ROOT / "README.md"
BRIEF_PATH = ROOT / "tasks" / "TASK-6.md"


def test_hash_matches_readme() -> None:
    got = verify_corpus_hash(str(CORPUS_PATH), str(README_PATH))
    assert got == "2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f"


def test_load_published_frame() -> None:
    verify_corpus_hash(str(CORPUS_PATH), str(README_PATH))
    frame_counts = load_frame_counts(str(BRIEF_PATH), str(README_PATH))
    conn = open_corpus(str(CORPUS_PATH))
    try:
        loaded = load_published_frame(conn, str(BRIEF_PATH), str(README_PATH))
    finally:
        conn.close()
    assert len(loaded["published"]) == frame_counts.published_expected
    videos = assign_groups(loaded["videos"])
    assert videos.attrs["n_unassigned_period"] == 0
    assert videos.attrs["n_unassigned_film"] == 0
    assert (
        videos.attrs["n_period_pre"] + videos.attrs["n_period_post"]
        == frame_counts.videos_expected
    )
    published = loaded["published"]
    counts = agreement_counts(published)
    assert counts["n_total"] == frame_counts.published_expected
    assert (
        counts["n_judgeable"]
        == counts["n_total"]
        - counts["n_empty_realized"]
        - counts["n_dur_le_0"]
        + counts["n_empty_and_zerodur"]
    )


def test_status_roundtrip(tmp_path) -> None:
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    Path(out_FILE).write_text("{}\n", encoding="utf-8")
    write_status(
        status_FILE,
        {"status": "complete", "outputs": {"out.json": sha256_file(out_FILE)}},
    )
    payload = read_completed_output(status_FILE, out_FILE)
    assert payload == b"{}\n"
