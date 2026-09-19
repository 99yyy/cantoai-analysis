"""Double and permute invariants: counts 2×, rates stay; hardcoded denom goes red."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "relations", ROOT / "scripts" / "relations.py"
)
assert SPEC is not None and SPEC.loader is not None
relations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relations)

from tests.test_output_check import CORPUS_PATH, CORPUS_SHA, output_check

FIXTURE = ROOT / "tests" / "fixtures" / "relations_probe"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _mini_corpus(path: Path, *, rare_mid: bool = False) -> None:
    """A+B syllables. Default glyphs have n_char=1 so rare_share stays under double.

    ``rare_mid=True`` plants five copies of one glyph (the 5–9 band that doubling
    pushes across the ``< 10`` cutoff).
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE videos(
            video_id TEXT PRIMARY KEY, title TEXT, upload_date TEXT
        );
        CREATE TABLE windows(
            uid TEXT PRIMARY KEY, video_id TEXT, tier TEXT
        );
        CREATE TABLE syllables(
            syl_id TEXT PRIMARY KEY, uid TEXT, video_id TEXT,
            char TEXT, jp_match TEXT, jp_realized TEXT, dur REAL
        );
        CREATE TABLE runs(git_sha TEXT);
        """
    )
    conn.execute(
        "INSERT INTO videos(video_id, title, upload_date) VALUES ('v1', '粵劇', '20240101')"
    )
    conn.execute(
        "INSERT INTO videos(video_id, title, upload_date) VALUES ('v2', '日常', '20250101')"
    )
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('w1', 'v1', 'A')")
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('w2', 'v2', 'B')")
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('w3', 'v2', 'C')")
    rows = [
        ("s1", "w1", "v1", "甲", "exact_default", "aa3", 0.1),
        ("s2", "w1", "v1", "乙", "tone", "bb2", 0.1),
        ("s3", "w2", "v2", "丙", "tone", "cc1", 0.1),
        ("s4", "w3", "v2", "丁", "tone", "dd1", 0.1),
    ]
    conn.executemany(
        "INSERT INTO syllables(syl_id, uid, video_id, char, jp_match, jp_realized, dur) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    if rare_mid:
        for i in range(5):
            conn.execute(
                "INSERT INTO syllables(syl_id, uid, video_id, char, jp_match, jp_realized, dur) "
                "VALUES (?, 'w1', 'v1', '戊', 'diff', 'ee1', 0.1)",
                (f"sm{i}",),
            )
    conn.execute("INSERT INTO runs(git_sha) VALUES ('probe')")
    conn.commit()
    conn.close()


def _write_brief(repo: Path, names: list[tuple[str, str]]) -> Path:
    md = repo / "tasks" / "TASK-9.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# TASK-9\n", "status: open\n", "```numbers\n"]
    for name, tol in names:
        lines.append(f"{name}  {tol}\n")
    lines.append("```\n")
    md.write_text("".join(lines), encoding="utf-8")
    return md


def _write_side(
    repo: Path,
    names: list[tuple[str, float, str]],
    *,
    worker: bool = True,
) -> None:
    sub = "sql" if worker else "mine_sql"
    out_name = "results.json" if worker else "mine.json"
    dest = repo / "tasks" / "TASK-9" / sub
    dest.mkdir(parents=True, exist_ok=True)
    payload = []
    for name, value, sql_name in names:
        src = FIXTURE / sql_name
        (dest / sql_name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        payload.append(
            {
                "name": name,
                "value": value,
                "n": 1,
                "query": f"tasks/TASK-9/{sub}/{sql_name}",
            }
        )
    out = repo / "tasks" / "TASK-9" / out_name
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _pin_readme(repo: Path, corpus: Path) -> None:
    (repo / "README.md").write_text(
        f"sha256: `{_sha256_file(corpus)}`\n", encoding="utf-8"
    )


def _run_main(repo: Path, corpus: Path, *extra: str) -> int:
    argv = [
        "relations.py",
        "--repo-root",
        str(repo),
        "--corpus",
        str(corpus),
        *extra,
    ]
    old = sys.argv
    sys.argv = argv
    try:
        return relations.main()
    finally:
        sys.argv = old


def test_family_classifies_declared_prefixes():
    assert relations.family("n_total_pre") == "count"
    assert relations.family("agree_film_pre") == "rate"
    assert relations.family("rare_share_post") == "rate"
    assert relations.family("rate_tone_pre_pm") == "rate"
    assert relations.family("gap_all_pp") == "rate"
    assert relations.family("did_film_pp") == "rate"


def test_family_rejects_unclassified_name():
    with pytest.raises(relations.Fail, match=r"matches no double/permute family"):
        relations.family("smoke_ok")


def test_ident_rejects_injection():
    with pytest.raises(relations.Fail, match=r"is not a simple name"):
        relations.ident("videos; drop")


def test_refuse_data_dir(tmp_path):
    data_DIR = tmp_path / "data"
    data_DIR.mkdir()
    dest = data_DIR / "corpus_double.sqlite"
    with pytest.raises(relations.Fail, match=r"refusing to write a temp corpus under"):
        relations.refuse_data_dir(dest, data_DIR)


def test_double_n_exactly_two_rate_stays(tmp_path):
    assert relations.check_double_value("r", "n_count", 2.0, 4.0, 0.0, [])
    fail: list[str] = []
    assert not relations.check_double_value("r", "n_count", 2.0, 3.0, 0.0, fail)
    assert "want exactly 2 *" in fail[0]
    fail = []
    assert relations.check_double_value("r", "rate_tone_pre_pm", 10.0, 10.0, 0.5, fail)
    assert fail == []
    fail = []
    assert not relations.check_double_value(
        "r", "rate_tone_pre_pm", 10.0, 20.0, 0.5, fail
    )
    assert "double 20, original 10" in fail[0]


def test_permute_must_match(tmp_path):
    fail: list[str] = []
    assert relations.check_permute_value("r", "n_count", 2.0, 2.0, 0.0, fail)
    assert not relations.check_permute_value("r", "n_count", 2.0, 4.0, 0.0, fail)
    assert "permute 4, original 2" in fail[-1]


def test_double_copies_rows_with_dup_prefix(tmp_path):
    src = tmp_path / "mini.sqlite"
    _mini_corpus(src)
    dest = tmp_path / "tmp" / "double.sqlite"
    relations.double_corpus(src, dest, tmp_path / "data")
    conn = sqlite3.connect(dest)
    try:
        n_v = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        n_w = conn.execute("SELECT COUNT(*) FROM windows").fetchone()[0]
        n_s = conn.execute("SELECT COUNT(*) FROM syllables").fetchone()[0]
        assert (n_v, n_w, n_s) == (4, 6, 8)
        dups = conn.execute(
            "SELECT video_id FROM videos WHERE video_id LIKE 'dup:%' ORDER BY 1"
        ).fetchall()
        assert dups == [("dup:v1",), ("dup:v2",)]
        uid = conn.execute(
            "SELECT uid, video_id FROM windows WHERE uid LIKE 'dup:%' ORDER BY 1"
        ).fetchall()
        assert uid == [("dup:w1", "dup:v1"), ("dup:w2", "dup:v2"), ("dup:w3", "dup:v2")]
        chars = conn.execute(
            "SELECT char FROM syllables WHERE syl_id LIKE 'dup:%'"
        ).fetchall()
        assert chars and all(c[0].startswith("dup:") for c in chars)
        orig_chars = conn.execute(
            "SELECT char FROM syllables WHERE syl_id NOT LIKE 'dup:%'"
        ).fetchall()
        assert orig_chars and all(not c[0].startswith("dup:") for c in orig_chars)
    finally:
        conn.close()


def test_permute_preserves_row_counts_and_keys(tmp_path):
    src = tmp_path / "mini.sqlite"
    _mini_corpus(src)
    dest = tmp_path / "tmp" / "perm.sqlite"
    relations.permute_corpus(src, dest, tmp_path / "data")
    a = sqlite3.connect(src)
    b = sqlite3.connect(dest)
    try:
        for table, key in (
            ("videos", "video_id"),
            ("windows", "uid"),
            ("syllables", "syl_id"),
        ):
            left = {r[0] for r in a.execute(f"SELECT {key} FROM {table}")}
            right = {r[0] for r in b.execute(f"SELECT {key} FROM {table}")}
            assert left == right
    finally:
        a.close()
        b.close()


def _green_task(repo: Path, corpus: Path) -> None:
    _pin_readme(repo, corpus)
    _write_brief(
        repo,
        [("n_count", "0"), ("rate_tone_pre_pm", "0.5"), ("rare_share_pre", "0.0005")],
    )
    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    try:
        n_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        rate = conn.execute(
            (FIXTURE / "rate_tone_pre_pm.sql").read_text(encoding="utf-8")
        ).fetchone()[0]
        rare = conn.execute(
            (FIXTURE / "rare_share_pre.sql").read_text(encoding="utf-8")
        ).fetchone()[0]
    finally:
        conn.close()
    _write_side(
        repo,
        [
            ("n_count", float(n_count), "n_count.sql"),
            ("rate_tone_pre_pm", float(rate), "rate_tone_pre_pm.sql"),
            ("rare_share_pre", float(rare), "rare_share_pre.sql"),
        ],
    )


def test_mini_task_double_and_permute_pass(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _green_task(repo, corpus)
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "relations: PASS" in out
    assert "double 3/3" in out
    assert "permute 3/3" in out
    assert "not data/" in out or "temp corpora under" in out


def test_hardcoded_rate_denominator_fails_double_original_replays(
    tmp_path, capsys
):
    """Must-go-red probe: COUNT(*) replaced by the live-corpus literal.

    Original replay still matches (output-check green). Double must go red.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _green_task(repo, corpus)
    sql_path = repo / "tasks" / "TASK-9" / "sql" / "rate_tone_pre_pm.sql"
    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    try:
        denom = conn.execute(
            """
            SELECT COUNT(*)
            FROM syllables s
            JOIN windows w ON s.uid = w.uid
            JOIN videos v ON s.video_id = v.video_id
            WHERE w.tier IN ('A', 'B')
            """
        ).fetchone()[0]
        orig_rate = conn.execute(sql_path.read_text(encoding="utf-8")).fetchone()[0]
    finally:
        conn.close()
    mutated = sql_path.read_text(encoding="utf-8").replace(
        "/ COUNT(*)", f"/ {int(denom)}"
    )
    assert "/ COUNT(*)" not in mutated
    sql_path.write_text(mutated, encoding="utf-8")

    replayed = output_check.run_sql(
        sqlite3.connect(f"file:{corpus}?mode=ro", uri=True),
        "results.json:rate_tone_pre_pm",
        sql_path,
        60.0,
    )
    assert output_check.close(replayed, float(orig_rate), 0.5)

    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert "rate_tone_pre_pm: double" in out
    assert "original" in out
    assert "relations: FAIL" in out


def test_without_char_prefix_mid_band_cutoff_moves(tmp_path, capsys, monkeypatch):
    """The listed rare_share invariance is why syllables.char is prefixed.

    Five tokens of one glyph: without namespacing char, doubling pushes
    n_char from 5 to 10 and rare_share moves. With the default prefix set
    it stays (see test_rare_share_stays_when_char_is_namespaced).
    """
    monkeypatch.setitem(
        relations.PREFIX_COLUMNS,
        "syllables",
        frozenset({"syl_id", "uid", "video_id"}),
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus, rare_mid=True)
    _green_task(repo, corpus)
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert "rare_share_pre: double" in out


def test_rare_share_stays_when_char_is_namespaced(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus, rare_mid=True)
    _green_task(repo, corpus)
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "double 3/3" in out


def test_corpus_hash_mismatch_prints_both_values(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    (repo / "README.md").write_text("sha256: `" + ("a" * 64) + "`\n", encoding="utf-8")
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1
    got = _sha256_file(corpus)
    assert got in out
    assert "a" * 64 in out


def test_does_not_write_under_data(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    data_DIR = repo / "data"
    data_DIR.mkdir()
    corpus = data_DIR / "corpus_v2.sqlite"
    _mini_corpus(corpus)
    _green_task(repo, corpus)
    before = _sha256_file(corpus)
    mtime = corpus.stat().st_mtime_ns
    code = _run_main(repo, corpus)
    assert code == 0
    assert _sha256_file(corpus) == before
    assert corpus.stat().st_mtime_ns == mtime
    assert list(data_DIR.iterdir()) == [corpus]


def test_temp_cleaned_up(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _green_task(repo, corpus)
    runner = tmp_path / "runner_temp"
    runner.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(runner))
    code = _run_main(repo, corpus)
    assert code == 0
    leftover = list(runner.glob("relations-*"))
    assert leftover == []


def test_live_task_6_pinned_corpus_sha():
    got = _sha256_file(CORPUS_PATH)
    assert got == CORPUS_SHA
