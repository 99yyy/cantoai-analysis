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


def _write_brief(
    repo: Path, names: list[tuple[str, str]], *, extra: str = ""
) -> Path:
    md = repo / "tasks" / "TASK-9.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# TASK-9\n", "status: open\n", "```numbers\n"]
    for name, tol in names:
        lines.append(f"{name}  {tol}\n")
    lines.append("```\n")
    if extra:
        lines.append(extra)
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


def test_unknown_task_flag_fails(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _green_task(repo, corpus)
    code = _run_main(repo, corpus, "--task", "99")
    out = capsys.readouterr().out
    assert code == 1
    assert "no tasks/TASK-99.md" in out
    assert "relations: FAIL" in out


def test_task_flag_skips_unclassified_other_brief(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _green_task(repo, corpus)
    (repo / "tasks" / "TASK-8.md").write_text(
        "# TASK-8\nstatus: open\n```numbers\nsmoke_ok  0\n```\n",
        encoding="utf-8",
    )
    sql8 = repo / "tasks" / "TASK-8" / "sql" / "n.sql"
    sql8.parent.mkdir(parents=True, exist_ok=True)
    sql8.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    (repo / "tasks" / "TASK-8" / "results.json").write_text(
        json.dumps(
            [
                {
                    "name": "smoke_ok",
                    "value": 2,
                    "n": 1,
                    "query": "tasks/TASK-8/sql/n.sql",
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    code_all = _run_main(repo, corpus)
    out_all = capsys.readouterr().out
    assert code_all == 1, out_all
    assert "matches no double/permute family" in out_all

    code = _run_main(repo, corpus, "--task", "9")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "only TASK-9" in out
    assert "TASK-8" not in out
    assert "relations: PASS" in out


# --- exclude (tier C) invariant and the published_expected anchor ----------

FRAME_AB = (
    "```frame\nwindows.tier IN ('A','B')\npublished_expected 3\n"
    "published_expected_tol 0\n```\n"
)


def _all_tiers_task(repo: Path, corpus: Path, *, extra: str) -> None:
    """The green task plus ``n_all``: COUNT over every tier (A+B+C = 4 rows).

    Original replay matches the written value, so output-check style checks
    stay green; only the exclude invariant can see that the count read tier C.
    """
    _pin_readme(repo, corpus)
    _write_brief(
        repo,
        [
            ("n_count", "0"),
            ("rate_tone_pre_pm", "0.5"),
            ("rare_share_pre", "0.0005"),
            ("n_all", "0"),
        ],
        extra=extra,
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
        n_all = conn.execute(
            (FIXTURE / "n_all_tiers.sql").read_text(encoding="utf-8")
        ).fetchone()[0]
    finally:
        conn.close()
    assert n_all == 4
    _write_side(
        repo,
        [
            ("n_count", float(n_count), "n_count.sql"),
            ("rate_tone_pre_pm", float(rate), "rate_tone_pre_pm.sql"),
            ("rare_share_pre", float(rare), "rare_share_pre.sql"),
            ("n_all", float(n_all), "n_all_tiers.sql"),
        ],
    )


def test_exclude_not_run_without_published_expected(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _all_tiers_task(repo, corpus, extra="")
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "exclude not run (frame has no published_expected)" in out
    assert "exclude by" not in out


def test_exclude_count_over_outside_frame_goes_red(tmp_path, capsys):
    """Must-go-red probe: a count that reads tier C, in a brief whose frame
    declares published_expected. Original replay is green (value matches)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _all_tiers_task(repo, corpus, extra=FRAME_AB)
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert "exclude by windows.tier IN ('A','B') removed 1 windows, 1 syllables" in out
    assert "frame.published_expected 3 = published syllables rows" in out
    assert (
        "results.json:n_all: on the published set only 3, original 4 (tol 0) -- "
        "this number depends on rows outside the frame"
    ) in out
    assert "exclude 3/4" in out
    assert "double 4/4" in out


def test_outside_frame_declaration_exempts_name_and_prints_it(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _all_tiers_task(
        repo, corpus, extra=FRAME_AB + "```outside_frame\nn_all  # reads every tier\n```\n"
    )
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "exclude 3/3 (1 outside_frame by declaration: n_all)" in out
    assert "depends on rows outside the frame" not in out


def test_outside_frame_unknown_name_fails(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _all_tiers_task(repo, corpus, extra=FRAME_AB + "```outside_frame\nn_nope\n```\n")
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert "TASK-9.md: outside_frame names 'n_nope' which is not in the numbers block" in out


def test_outside_frame_empty_and_duplicate_fail():
    tol = {"n_all": 0.0}
    with pytest.raises(relations.Fail) as ei:
        relations.parse_outside_frame_block("b", "```outside_frame\n# only\n```\n", tol)
    assert str(ei.value) == "b: the outside_frame block is empty"
    with pytest.raises(relations.Fail) as ei:
        relations.parse_outside_frame_block("b", "```outside_frame\nn_all\nn_all\n```\n", tol)
    assert str(ei.value) == "b: outside_frame lists n_all twice"
    assert relations.parse_outside_frame_block("b", "no fence", tol) == frozenset()


def test_outside_frame_closure_reaches_derived_names_only():
    routes = {
        "n_all": ("sql", Path("a.sql")),
        "n_count": ("sql", Path("b.sql")),
        "gap_x_pp": ("derived", "100 * n_all / n_count"),
        "gap_y_pp": ("derived", "gap_x_pp * 2"),
        "gap_z_pp": ("derived", "n_count / 2"),
    }
    got = relations.outside_frame_closure(frozenset({"n_all"}), routes)
    assert got == frozenset({"n_all", "gap_x_pp", "gap_y_pp"})


def test_published_anchor_mismatch_fails(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _green_task(repo, corpus)
    md = repo / "tasks" / "TASK-9.md"
    md.write_text(
        md.read_text(encoding="utf-8")
        + "```frame\nwindows.tier IN ('A','B')\npublished_expected 99\n```\n",
        encoding="utf-8",
    )
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert (
        "TASK-9: frame.published_expected is 99 but the pinned corpus holds 3 "
        "published syllables rows (tol 0)"
    ) in out


def test_rare_cutoff_that_reads_tier_c_moves_under_exclude(tmp_path, capsys):
    """Ten tokens of an A+B glyph planted in the tier-C window: on the full
    table the glyph is common (n_char 11), without tier C it is rare. This is
    the TASK-6 / TASK-7 situation; the brief must say so in outside_frame."""
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    conn = sqlite3.connect(corpus)
    for i in range(10):
        conn.execute(
            "INSERT INTO syllables(syl_id, uid, video_id, char, jp_match, jp_realized, dur) "
            "VALUES (?, 'w3', 'v2', '丙', 'tone', 'cc1', 0.1)",
            (f"c{i}",),
        )
    conn.commit()
    conn.close()
    _green_task(repo, corpus)
    md = repo / "tasks" / "TASK-9.md"
    md.write_text(md.read_text(encoding="utf-8") + FRAME_AB, encoding="utf-8")
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert "results.json:rare_share_pre: on the published set only 1, original 0.6666666666666666 (tol 0.0005)" in out
    md.write_text(
        md.read_text(encoding="utf-8") + "```outside_frame\nrare_share_pre\n```\n",
        encoding="utf-8",
    )
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "exclude 2/2 (1 outside_frame by declaration: rare_share_pre)" in out


def test_published_expected_without_predicate_fails(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _green_task(repo, corpus)
    md = repo / "tasks" / "TASK-9.md"
    md.write_text(
        md.read_text(encoding="utf-8") + "```frame\npublished_expected 3\n```\n",
        encoding="utf-8",
    )
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert (
        "TASK-9: frame declares published_expected but no <table>.<column> "
        "predicate line defines the published set"
    ) in out


def test_predicate_on_unknown_table_or_column_fails(tmp_path):
    corpus = tmp_path / "mini.sqlite"
    _mini_corpus(corpus)
    with pytest.raises(relations.Fail) as ei:
        relations.exclude_corpus(corpus, tmp_path / "x.sqlite", tmp_path / "data", [("nope", "tier", "= 'A'")])
    assert "names table 'nope', which is not in gate_config tables" in str(ei.value)
    with pytest.raises(relations.Fail) as ei:
        relations.exclude_corpus(corpus, tmp_path / "y.sqlite", tmp_path / "data", [("windows", "nope", "= 'A'")])
    assert str(ei.value) == "relations: windows has no column nope (frame predicate)"
    with pytest.raises(relations.Fail) as ei:
        relations.exclude_corpus(corpus, tmp_path / "z.sqlite", tmp_path / "data", [])
    assert str(ei.value) == "relations: exclude needs at least one frame predicate"


def test_exclude_cascades_through_refs_and_null_is_unpublished(tmp_path):
    corpus = tmp_path / "mini.sqlite"
    _mini_corpus(corpus)
    conn = sqlite3.connect(corpus)
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('w4', 'v2', NULL)")
    conn.execute(
        "INSERT INTO syllables(syl_id, uid, video_id, char, jp_match, jp_realized, dur) "
        "VALUES ('s5', 'w4', 'v2', '戊', 'tone', 'ee1', 0.1)"
    )
    conn.commit()
    conn.close()
    removed = relations.exclude_corpus(
        corpus, tmp_path / "exc.sqlite", tmp_path / "data", [("windows", "tier", "IN ('A','B')")]
    )
    assert removed == {"videos": 0, "windows": 2, "syllables": 2}
    c = sqlite3.connect(tmp_path / "exc.sqlite")
    assert c.execute("SELECT COUNT(*) FROM windows").fetchone()[0] == 2
    assert c.execute("SELECT COUNT(*) FROM syllables").fetchone()[0] == 3
    assert c.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 2
    assert relations.published_units(c) == 3
    c.close()


def test_families_and_prefix_columns_come_from_config():
    cfg = relations.CONFIG
    assert relations.TABLES == tuple(cfg["tables"])
    assert relations.UNIT_TABLE == cfg["unit_table"]
    assert "char" in relations.PREFIX_COLUMNS["syllables"]
    assert relations.PREFIX_COLUMNS["windows"] == frozenset({"uid", "video_id"})
    for prefix in cfg["families"]["count"]["prefix"]:
        assert relations.family(prefix + "x") == "count"
    with pytest.raises(relations.Fail) as ei:
        relations.family("zzz_nothing")
    assert str(ei.value).startswith("relations: zzz_nothing matches no double/permute family (count: n_; rate:")
    src = (ROOT / "scripts" / "relations.py").read_text(encoding="utf-8")
    for token in ("'A'", "\"C\"", "syllables", "windows", "rare_share"):
        # names appear only in prose (docstrings/comments), never in code paths
        code_lines = [
            l for l in src.splitlines()
            if token in l and not l.strip().startswith("#") and not l.strip().startswith(("*", "\"", "'"))
        ]
        assert code_lines == [], (token, code_lines)


# --- anchor before any output, and score routes left to output-check ------


def test_anchor_is_checked_before_any_output(tmp_path, capsys):
    """A wrong published count fails on the brief's own pull request, before
    any agent has been launched on it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _pin_readme(repo, corpus)
    _write_brief(
        repo,
        [("n_count", "0")],
        extra="```frame\nwindows.tier IN ('A','B')\npublished_expected 99\n```\n",
    )
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert (
        "TASK-9: frame.published_expected is 99 but the pinned corpus holds 3 "
        "published syllables rows (tol 0)"
    ) in out
    assert "no output yet" in out


def test_anchor_before_any_output_green(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _pin_readme(repo, corpus)
    _write_brief(repo, [("n_count", "0")], extra=FRAME_AB)
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "frame.published_expected 3 = published syllables rows" in out
    assert "no output yet; double/permute not run" in out


def _score_task_on_mini(repo: Path, corpus: Path, extra_rows: list[dict], names: list[tuple[str, str]]) -> None:
    """n_count by SQL, rate_cer_m_pm scored from predictions, plus ``extra_rows``."""
    _pin_readme(repo, corpus)
    _write_brief(
        repo,
        [("n_count", "0"), ("rate_cer_m_pm", "0.5"), *names],
        extra="```eval\nset benchmarks/demo\n```\n",
    )
    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    try:
        n_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    finally:
        conn.close()
    _write_side(repo, [("n_count", float(n_count), "n_count.sql")])
    manifest = repo / "benchmarks" / "demo" / "manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{"id": "a", "ref": "天氣好好"}\n', encoding="utf-8")
    pred = repo / "tasks" / "TASK-9" / "pred" / "m.jsonl"
    pred.parent.mkdir(parents=True, exist_ok=True)
    pred.write_text('{"id": "a", "hyp": "天氣好"}\n', encoding="utf-8")
    (pred.parent / "m.run.json").write_text(
        json.dumps(
            {
                "script_commit": "a" * 40,
                "model": "example/asr-small",
                "model_revision": "b" * 40,
                "decoding": {"language": "yue"},
                "device": "cpu",
                "dirty": False,
            }
        ),
        encoding="utf-8",
    )
    out_path = repo / "tasks" / "TASK-9" / "results.json"
    rows = json.loads(out_path.read_text(encoding="utf-8"))
    rows.append(
        {
            "name": "rate_cer_m_pm",
            "value": 250.0,
            "n": 4,
            "query": "score:cer:tasks/TASK-9/pred/m.jsonl",
        }
    )
    rows.extend(extra_rows)
    out_path.write_text(json.dumps(rows), encoding="utf-8")


def test_score_routes_are_constant_on_every_copy(tmp_path, capsys):
    """A number scored from predictions does not read the corpus: relations
    replays it once and it passes double, permute and exclude as a constant."""
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _score_task_on_mini(repo, corpus, [], [])
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 0, out
    assert (
        "results.json 1 score route(s) replayed from predictions, constant on every "
        "copy: rate_cer_m_pm"
    ) in out
    assert "double 2/2 permute 2/2" in out


def test_derived_name_mixing_score_and_corpus_is_still_checked(tmp_path, capsys):
    """``+ 0 * rate_cer_m_pm`` must not hide a hard-coded denominator."""
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    _mini_corpus(corpus)
    _score_task_on_mini(
        repo,
        corpus,
        [
            {
                "name": "rate_hit_pm",
                "value": 1000.0,
                "n": 1,
                "query": "derived: 1000 * n_count / 2 + 0 * rate_cer_m_pm",
            }
        ],
        [("rate_hit_pm", "0.5")],
    )
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 1, out
    assert "results.json:rate_hit_pm: double 2000, original 1000 (tol 0.5)" in out, out
    assert "cannot be resolved" not in out, out


def test_pred_tables_follow_double_permute_and_exclude(tmp_path, capsys):
    """A count joined to pred_<stem> doubles, survives permute, and ignores excluded rows."""
    repo = tmp_path / "repo"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    conn = sqlite3.connect(corpus)
    conn.executescript(
        """
        CREATE TABLE videos(video_id TEXT PRIMARY KEY, title TEXT, upload_date TEXT);
        CREATE TABLE windows(uid TEXT PRIMARY KEY, video_id TEXT, tier TEXT);
        CREATE TABLE syllables(
            syl_id TEXT PRIMARY KEY, uid TEXT, video_id TEXT,
            char TEXT, jp_match TEXT, jp_realized TEXT, dur REAL
        );
        CREATE TABLE runs(git_sha TEXT);
        INSERT INTO videos VALUES ('v1', 't', '20240101');
        INSERT INTO windows VALUES ('w1', 'v1', 'A');
        INSERT INTO windows VALUES ('w2', 'v1', 'C');
        INSERT INTO syllables VALUES ('s1', 'w1', 'v1', '甲', 'exact_default', 'aa1', 0.1);
        INSERT INTO syllables VALUES ('s2', 'w2', 'v1', '乙', 'tone', 'bb1', 0.1);
        INSERT INTO runs VALUES ('probe');
        """
    )
    conn.commit()
    conn.close()
    _pin_readme(repo, corpus)
    _write_brief(
        repo,
        [("n_pred_a", "0")],
        extra=(
            "```frame\n"
            "windows.tier = 'A'\n"
            "published_expected 1\n"
            "```\n"
            "```pred\n"
            "g2p\n"
            "```\n"
        ),
    )
    sql = (
        "SELECT COUNT(*) FROM syllables s\n"
        "JOIN windows w ON s.uid = w.uid\n"
        "JOIN pred_g2p p ON p.id = s.syl_id\n"
        "WHERE w.tier = 'A'\n"
    )
    card = {
        "script_commit": "a" * 40,
        "model": "example/g2p",
        "model_revision": "b" * 40,
        "decoding": {"language": "yue"},
        "device": "cpu",
        "dirty": False,
    }
    for side, sub, out_name, hyp2 in (
        ("worker", "sql", "results.json", "zz9"),
        ("verifier", "mine_sql", "mine.json", "yy9"),
    ):
        pred_dir = repo / "tasks" / "TASK-9" / ("pred" if side == "worker" else "mine_pred")
        pred_dir.mkdir(parents=True)
        (pred_dir / "g2p.jsonl").write_text(
            '{"id": "s1", "hyp": "aa1"}\n{"id": "s2", "hyp": "' + hyp2 + '"}\n',
            encoding="utf-8",
        )
        (pred_dir / "g2p.run.json").write_text(json.dumps(card), encoding="utf-8")
        sql_dir = repo / "tasks" / "TASK-9" / sub
        sql_dir.mkdir(parents=True, exist_ok=True)
        (sql_dir / "n_pred_a.sql").write_text(sql, encoding="utf-8")
        payload = [
            {
                "name": "n_pred_a",
                "value": 1,
                "n": 1,
                "query": f"tasks/TASK-9/{sub}/n_pred_a.sql",
            }
        ]
        (repo / "tasks" / "TASK-9" / out_name).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    code = _run_main(repo, corpus)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "double 1/1" in out
    assert "permute 1/1" in out
    assert "exclude 1/1" in out
    assert "loaded pred_g2p" in out
