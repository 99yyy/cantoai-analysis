"""Identities fence: evaluate on replayed SQL routes; skip derived tautologies.

The TASK-6 film/other hole is that
``n_judgeable_film_* + n_judgeable_other_* = n_judgeable_*`` does not hold
once an untitled video contributes judgeable syllables. The probe below is a
fixture mini-task under tests/fixtures/identities_probe/ so this PR owns a
real red proof without writing TASK-6 worker and verifier SQL for the new
names.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tests.test_output_check import (
    CORPUS_PATH,
    CORPUS_SHA,
    ROOT,
    _write_brief,
    output_check,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True)
    try:
        yield c
    finally:
        c.close()

FIXTURE = ROOT / "tests" / "fixtures" / "identities_probe"

FILM_OTHER_EQ_ALL = (
    "n_judgeable_film_pre + n_judgeable_other_pre = n_judgeable_pre  0"
)
THREE_TERM = (
    "n_judgeable_film_pre + n_judgeable_other_pre + "
    "n_judgeable_unassigned_film_pre = n_judgeable_pre  0"
)


def _mini_corpus(path: Path, untitled_judgeable: int = 0) -> sqlite3.Connection:
    """A+B pre windows. Optional untitled video with judgeable syllables."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            upload_date TEXT
        );
        CREATE TABLE windows (
            uid TEXT PRIMARY KEY,
            video_id TEXT,
            tier TEXT
        );
        CREATE TABLE syllables (
            syl_id TEXT PRIMARY KEY,
            uid TEXT,
            video_id TEXT,
            jp_realized TEXT,
            dur REAL
        );
        CREATE TABLE runs (git_sha TEXT);
        """
    )
    conn.execute(
        "INSERT INTO videos(video_id, title, upload_date) VALUES ('f', '粵劇一齣', '20240101')"
    )
    conn.execute(
        "INSERT INTO videos(video_id, title, upload_date) VALUES ('o', '日常傾偈', '20240101')"
    )
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('wf', 'f', 'A')")
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('wo', 'o', 'B')")
    conn.execute(
        "INSERT INTO syllables(syl_id, uid, video_id, jp_realized, dur) "
        "VALUES ('sf', 'wf', 'f', 'aa3', 0.12)"
    )
    conn.execute(
        "INSERT INTO syllables(syl_id, uid, video_id, jp_realized, dur) "
        "VALUES ('so', 'wo', 'o', 'bb6', 0.09)"
    )
    # Non-judgeable and non-A/B rows must not enter any count.
    conn.execute(
        "INSERT INTO syllables(syl_id, uid, video_id, jp_realized, dur) "
        "VALUES ('sf0', 'wf', 'f', 'aa3', 0.0)"
    )
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('wc', 'o', 'C')")
    conn.execute(
        "INSERT INTO syllables(syl_id, uid, video_id, jp_realized, dur) "
        "VALUES ('sc', 'wc', 'o', 'cc1', 0.2)"
    )
    if untitled_judgeable:
        conn.execute(
            "INSERT INTO videos(video_id, title, upload_date) VALUES ('u', '', '20240101')"
        )
        conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('wu', 'u', 'A')")
        for i in range(untitled_judgeable):
            conn.execute(
                "INSERT INTO syllables(syl_id, uid, video_id, jp_realized, dur) "
                "VALUES (?, 'wu', 'u', 'uu1', 0.11)",
                (f"su{i}",),
            )
    conn.execute("INSERT INTO runs(git_sha) VALUES ('probe')")
    conn.commit()
    return conn


def _alias_sql(text: str) -> str:
    """A second implementation: aliases, not a copy of the worker statement."""
    return (
        text.replace("FROM syllables s", "FROM syllables AS sy")
        .replace("JOIN windows w ", "JOIN windows AS win ")
        .replace("JOIN videos v ", "JOIN videos AS vid ")
        .replace("s.", "sy.")
        .replace("w.", "win.")
        .replace("v.", "vid.")
    )


def _install_sql(task_dir: Path, names: list[str], aliased: bool = False) -> None:
    dest_dir = task_dir / ("mine_sql" if aliased else "sql")
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = (FIXTURE / f"{name}.sql").read_text(encoding="utf-8")
        if aliased:
            src = _alias_sql(src)
        (dest_dir / f"{name}.sql").write_text(src, encoding="utf-8")


def _write_output(
    path: Path,
    rows: list[tuple[str, float, str]],
    n: int = 4,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"name": name, "value": value, "n": n, "query": query}
        for name, value, query in rows
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_parse_identity_expr_collects_names_not_frame_fields():
    names, fields = output_check.parse_identity_expr(
        "t",
        "n_judgeable_film_pre + n_judgeable_other_pre + "
        "n_judgeable_unassigned_film_pre",
    )
    assert names == {
        "n_judgeable_film_pre",
        "n_judgeable_other_pre",
        "n_judgeable_unassigned_film_pre",
    }
    assert fields == set()
    names, fields = output_check.parse_identity_expr(
        "t", "n_videos_pre + n_videos_post + n_unassigned_period"
    )
    names_r, fields_r = output_check.parse_identity_expr("t", "frame.videos_expected")
    assert names_r == set()
    assert fields_r == {"videos_expected"}


def test_eval_derived_binds_frame_field():
    got = output_check.eval_derived(
        "t",
        "n_videos_pre + n_videos_post + n_unassigned_period",
        {"n_videos_pre": 391.0, "n_videos_post": 176.0, "n_unassigned_period": 0.0},
        {"videos_expected": 567.0},
    )
    want = output_check.eval_derived(
        "t", "frame.videos_expected", {}, {"videos_expected": 567.0}
    )
    assert got == want == 567.0


def test_eval_derived_without_frame_rejects_attribute():
    with pytest.raises(output_check.Fail, match=r"declared names"):
        output_check.eval_derived("t", "frame.videos_expected", {})


def test_parse_identities_rejects_unknown_number_name(tmp_path):
    md = _write_brief(
        tmp_path,
        "9",
        extra_numbers="n_b  0\n",
        identities_block="n_count + n_b = n_missing  0\n",
    )
    with pytest.raises(
        output_check.Fail, match=r"identities names 'n_missing' which is not"
    ):
        output_check.parse_brief(md)


def test_parse_identities_rejects_unknown_frame_field(tmp_path):
    md = _write_brief(
        tmp_path,
        "9",
        frame_block="videos_expected 4\n",
        identities_block="n_count = frame.nope  0\n",
    )
    with pytest.raises(
        output_check.Fail, match=r"identities names frame.nope which is not"
    ):
        output_check.parse_brief(md)


def test_parse_identities_empty_block_fails(tmp_path):
    md = _write_brief(tmp_path, "9", identities_block="# nothing\n")
    with pytest.raises(output_check.Fail, match=r"the identities block is empty"):
        output_check.parse_brief(md)


def test_identity_sql_routed_requires_every_declared_name():
    declared = {"a": 0.0, "b": 0.0, "c": 0.0}
    routes = {
        "a": ("sql", Path("a.sql")),
        "b": ("sql", Path("b.sql")),
        "c": ("derived", "a + b"),
    }
    assert output_check.identity_sql_routed({"a", "b"}, declared, routes) is True
    assert output_check.identity_sql_routed({"a", "b", "c"}, declared, routes) is False
    assert output_check.identity_sql_routed(set(), declared, routes) is False


def test_identity_skipped_when_rhs_is_derived():
    """If evaluated, a + b = c would fail (1+1 vs 1). Skip because c is derived."""
    fail: list[str] = []
    ident = output_check.Identity("a + b", "c", 0.0, "a + b = c  0")
    held, skipped = output_check.check_identities(
        "9",
        "results.json",
        (ident,),
        {"a": 0.0, "b": 0.0, "c": 0.0},
        {"a": 1.0, "b": 1.0, "c": 1.0},
        {
            "a": ("sql", Path("a.sql")),
            "b": ("sql", Path("b.sql")),
            "c": ("derived", "a"),
        },
        {},
        fail,
    )
    assert fail == []
    assert held == []
    assert skipped == ["a + b = c  0"]


def test_identity_fails_when_all_sql_and_values_disagree():
    fail: list[str] = []
    ident = output_check.Identity("a + b", "c", 0.0, "a + b = c  0")
    held, skipped = output_check.check_identities(
        "9",
        "results.json",
        (ident,),
        {"a": 0.0, "b": 0.0, "c": 0.0},
        {"a": 1.0, "b": 1.0, "c": 1.0},
        {
            "a": ("sql", Path("a.sql")),
            "b": ("sql", Path("b.sql")),
            "c": ("sql", Path("c.sql")),
        },
        {},
        fail,
    )
    assert skipped == []
    assert held == []
    assert fail == [
        "TASK-9: results.json: identity a + b = c -> 2 = 1 does not hold (tol 0)"
    ]


def test_identity_does_not_merge_worker_and_verifier_dicts():
    """Worker derived c would make a+b=c a tautology; verifier SQL must still fail.

    If the checker merged the two replayed dicts, verifier could pick up
    worker's derived c and the identity would go green.
    """
    ident = output_check.Identity("a + b", "c", 0.0, "a + b = c  0")
    declared = {"a": 0.0, "b": 0.0, "c": 0.0}
    w_fail: list[str] = []
    w_held, w_skipped = output_check.check_identities(
        "9",
        "results.json",
        (ident,),
        declared,
        {"a": 1.0, "b": 1.0, "c": 2.0},
        {
            "a": ("sql", Path("wa.sql")),
            "b": ("sql", Path("wb.sql")),
            "c": ("derived", "a + b"),
        },
        {},
        w_fail,
    )
    assert w_fail == []
    assert w_held == []
    assert w_skipped == ["a + b = c  0"]

    v_fail: list[str] = []
    v_held, v_skipped = output_check.check_identities(
        "9",
        "mine.json",
        (ident,),
        declared,
        {"a": 1.0, "b": 1.0, "c": 3.0},
        {
            "a": ("sql", Path("va.sql")),
            "b": ("sql", Path("vb.sql")),
            "c": ("sql", Path("vc.sql")),
        },
        {},
        v_fail,
    )
    assert v_skipped == []
    assert v_held == []
    assert v_fail == [
        "TASK-9: mine.json: identity a + b = c -> 2 = 3 does not hold (tol 0)"
    ]


def test_check_identities_source_does_not_hardcode_567():
    src = (ROOT / "scripts" / "output_check.py").read_text(encoding="utf-8")
    start = src.index("def check_identities")
    end = src.index("\ndef parse_rows")
    assert "567" not in src[start:end]


def _film_fixture_task(
    repo: Path,
    untitled_judgeable: int,
    identity: str,
    include_unassigned: bool,
) -> tuple[Path, sqlite3.Connection]:
    names = ["n_judgeable_film_pre", "n_judgeable_other_pre", "n_judgeable_pre"]
    extra = "n_judgeable_other_pre  0\nn_judgeable_pre  0\n"
    if include_unassigned:
        names.append("n_judgeable_unassigned_film_pre")
        extra = (
            "n_judgeable_other_pre  0\n"
            "n_judgeable_unassigned_film_pre  0\n"
            "n_judgeable_pre  0\n"
        )
    md = _write_brief(
        repo,
        "9",
        name="n_judgeable_film_pre",
        extra_numbers=extra,
        identities_block=identity + "\n",
    )
    task_dir = repo / "tasks" / "TASK-9"
    _install_sql(task_dir, names, aliased=False)
    db = repo / "mini.sqlite"
    conn = _mini_corpus(db, untitled_judgeable=untitled_judgeable)
    film = 1.0
    other = 1.0
    unassigned = float(untitled_judgeable)
    all_j = film + other + unassigned
    w_rows = [
        (
            "n_judgeable_film_pre",
            film,
            "tasks/TASK-9/sql/n_judgeable_film_pre.sql",
        ),
        (
            "n_judgeable_other_pre",
            other,
            "tasks/TASK-9/sql/n_judgeable_other_pre.sql",
        ),
        (
            "n_judgeable_pre",
            all_j,
            "tasks/TASK-9/sql/n_judgeable_pre.sql",
        ),
    ]
    if include_unassigned:
        w_rows.insert(
            2,
            (
                "n_judgeable_unassigned_film_pre",
                unassigned,
                "tasks/TASK-9/sql/n_judgeable_unassigned_film_pre.sql",
            ),
        )
    _write_output(task_dir / "results.json", w_rows, n=4)
    return md, conn


def test_film_other_identity_holds_without_untitled(tmp_path, capsys):
    md, conn = _film_fixture_task(tmp_path, 0, FILM_OTHER_EQ_ALL, False)
    try:
        fail: list[str] = []
        output_check.check_task(
            tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
        )
    finally:
        conn.close()
    out = capsys.readouterr().out
    assert fail == []
    assert "identity n_judgeable_film_pre + n_judgeable_other_pre = n_judgeable_pre" in out
    assert "skipped" not in out


def test_empty_title_breaks_film_other_identity_when_sql_routed(tmp_path, capsys):
    """Must-go-red probe: all three terms SQL-routed; untitled judgeable syllables.

    ``film + other = all`` holds on titled videos alone. Injecting an empty
    title with ≥1 A/B window and ≥1 judgeable syllable makes it fail.
    """
    md, conn = _film_fixture_task(tmp_path, 2, FILM_OTHER_EQ_ALL, False)
    try:
        fail: list[str] = []
        output_check.check_task(
            tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
        )
    finally:
        conn.close()
    out = capsys.readouterr().out
    hits = [m for m in fail if "does not hold" in m]
    assert hits, out
    assert any(
        "n_judgeable_film_pre + n_judgeable_other_pre = n_judgeable_pre" in m
        and "-> 2 = 4 does not hold" in m
        for m in hits
    ), fail


def test_three_term_identity_holds_after_empty_title_when_unassigned_is_sql(
    tmp_path, capsys
):
    md, conn = _film_fixture_task(tmp_path, 2, THREE_TERM, True)
    try:
        fail: list[str] = []
        output_check.check_task(
            tmp_path, md, conn, 60.0, None, None, fail, CORPUS_SHA
        )
    finally:
        conn.close()
    out = capsys.readouterr().out
    assert fail == [], fail
    assert "n_judgeable_unassigned_film_pre" in out
    assert "skipped" not in out


def test_task_6_film_identities_skipped_on_derived_standins(conn, capsys):
    """TASK-6 unassigned names are derived leftovers until worker/verifier SQL."""
    md = ROOT / "tasks" / "TASK-6.md"
    fail: list[str] = []
    output_check.check_task(ROOT, md, conn, 60.0, None, None, fail, CORPUS_SHA)
    out = capsys.readouterr().out
    assert fail == []
    assert "41/41 n declared" in out
    assert "skipped 2 identities (not all SQL-routed)" in out
