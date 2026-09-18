"""Every src assertion message is tripped by calling an unmocked src function."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest

from src.agreement import assert_no_null_jp_match
from src.bootstrap import (
    assert_bootstrap_B,
    assert_inconclusive_when_unreliable,
    assert_seeds_distinct,
    make_stratum_seeds,
)
from src.frame import (
    assert_published_count,
    assert_syllables_count,
    assert_tier_matches_window,
    assert_videos_count,
    assert_windows_count,
)
from src.groups import assert_no_film_overlap, assert_no_period_overlap
from src.hashing import readme_sha256, verify_corpus_hash
from src.joins import checked_merge
from src.measures import (
    assert_no_measure_sentinel,
    assert_status_matches_values,
    attach_agreement,
    ensure_unique_columns,
    flatten_key,
)
from src.status_io import read_completed_output, write_json_atomic, write_status
from src.tables import quote_ident
from src.weights import assert_stratum_weights, stratum_weights
from src.write_results import eval_derived, n_for, run_sql_file


def test_corpus_sha256_mismatch(tmp_path):
    corpus_FILE = tmp_path / "c.sqlite"
    corpus_FILE.write_bytes(b"not-the-corpus")
    readme_FILE = tmp_path / "README.md"
    readme_FILE.write_text(
        "sha256: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"^corpus sha256 does not match README.md"):
        verify_corpus_hash(str(corpus_FILE), str(readme_FILE))


def test_readme_missing_sha256(tmp_path):
    readme_FILE = tmp_path / "README.md"
    readme_FILE.write_text("no hash here\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"^README\.md records no sha256 for the corpus"):
        readme_sha256(str(readme_FILE))


def test_table_name_not_identifier():
    with pytest.raises(ValueError, match=r"^table name is not a simple identifier"):
        quote_ident("syllables; drop")


def test_checked_merge_unknown_join():
    left = pd.DataFrame({"uid": [1]})
    right = pd.DataFrame({"uid": [1]})
    with pytest.raises(ValueError, match=r"^checked_merge join_name is not a declared join"):
        checked_merge(left, right, "not_a_join")


def test_checked_merge_syllables_windows_count():
    left = pd.DataFrame({"uid": [1, 2], "x": [0, 1]})
    right = pd.DataFrame({"uid": [1, 2], "y": [0, 1]})
    with pytest.raises(
        ValueError, match=r"^checked_merge syllables_windows: row count is not 171867"
    ):
        checked_merge(left, right, "syllables_windows")


def test_checked_merge_published_videos_count():
    left = pd.DataFrame({"video_id": ["a"], "x": [0]})
    right = pd.DataFrame({"video_id": ["a"], "y": [1]})
    with pytest.raises(
        ValueError,
        match=r"^checked_merge published_syllables_videos: row count is not 164693",
    ):
        checked_merge(left, right, "published_syllables_videos")


def test_videos_count():
    with pytest.raises(ValueError, match=r"^videos row count is outside the declared interval"):
        assert_videos_count(0)


def test_windows_count():
    with pytest.raises(ValueError, match=r"^windows row count is outside the declared interval"):
        assert_windows_count(0)


def test_syllables_count():
    with pytest.raises(
        ValueError, match=r"^syllables row count is outside the declared interval"
    ):
        assert_syllables_count(0)


def test_published_count():
    with pytest.raises(
        ValueError, match=r"^published A\+B syllable count is outside the declared interval"
    ):
        assert_published_count(0)


def test_tier_mismatch():
    df = pd.DataFrame({"tier": ["A"], "window_tier": ["B"]})
    with pytest.raises(ValueError, match=r"^syllable tier does not match window tier"):
        assert_tier_matches_window(df)


def test_period_overlap():
    pre = pd.Series([True, False])
    post = pd.Series([True, True])
    with pytest.raises(ValueError, match=r"^period overlap: a row matched both pre and post"):
        assert_no_period_overlap(pre, post)


def test_film_overlap():
    film = pd.Series([True, False])
    other = pd.Series([True, False])
    with pytest.raises(ValueError, match=r"^film overlap: a row matched both film and other"):
        assert_no_film_overlap(film, other)


def test_null_jp_match():
    df = pd.DataFrame({"jp_match": [None, "exact_default"]})
    judgeable = pd.Series([True, True])
    with pytest.raises(ValueError, match=r"^judgeable syllable has NULL jp_match"):
        assert_no_null_jp_match(df, judgeable)


def test_stratum_weights():
    w = np.ones(2)
    N_h = np.array([10.0, 20.0])
    n_h = np.array([5.0, 8.0])
    with pytest.raises(
        ValueError, match=r"^stratum weights do not equal N_h divided by n_h_judgeable"
    ):
        assert_stratum_weights(w, N_h, n_h)


def test_stratum_weights_ok():
    N_h = np.array([10.0, 20.0])
    n_h = np.array([5.0, 8.0])
    w = stratum_weights(N_h, n_h)
    assert_stratum_weights(w, N_h, n_h)


def test_seeds_not_distinct():
    with pytest.raises(ValueError, match=r"^bootstrap stratum seeds are not pairwise distinct"):
        assert_seeds_distinct({"a": 1, "b": 1})


def test_seeds_distinct_ok():
    seeds = make_stratum_seeds(20250918, ["film_pre", "film_post", "other_pre", "other_post"])
    assert len(set(seeds.values())) == 4


def test_bootstrap_B():
    with pytest.raises(ValueError, match=r"^bootstrap B is below 1000"):
        assert_bootstrap_B(10)


def test_ci_unreliable_conclusion():
    with pytest.raises(
        ValueError, match=r"^ci_unreliable row must carry conclusion=inconclusive"
    ):
        assert_inconclusive_when_unreliable(1, "estimated")


def test_flatten_key_separator():
    with pytest.raises(
        ValueError, match=r"^flattened key separator occurs inside a key segment"
    ):
        flatten_key(["a", "b\x1fc"], sep="\x1f")


def test_duplicate_column():
    df = pd.DataFrame({"agreement": [1.0]})
    with pytest.raises(ValueError, match=r"^duplicate column in output frame"):
        ensure_unique_columns(df, "agreement")


def test_status_matches_values():
    values = pd.Series([1.0, None], dtype="Float64")
    status = pd.Series(["ok", "ok"])
    with pytest.raises(
        ValueError, match=r"^measure status ok is not exactly the non-NULL value set"
    ):
        assert_status_matches_values(values, status)


def test_forbidden_status():
    values = pd.Series([pd.NA], dtype="Float64")
    status = pd.Series(["unknown"])
    with pytest.raises(
        ValueError, match=r"^unknown and other are not allowed measure status values"
    ):
        assert_status_matches_values(values, status)


def test_measure_sentinel():
    values = pd.Series([0.0], dtype="Float64")
    status = pd.Series(["ok"])
    n_j = pd.Series([0])
    with pytest.raises(ValueError, match=r"^measure sentinel written with status ok"):
        assert_no_measure_sentinel(values, status, n_j)


def test_status_not_complete(tmp_path):
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    write_status(status_FILE, {"status": "running"})
    write_json_atomic(out_FILE, {"x": 1})
    with pytest.raises(ValueError, match=r"^STATUS\.json is not complete"):
        read_completed_output(status_FILE, out_FILE)


def test_status_sha256_mismatch(tmp_path):
    status_FILE = str(tmp_path / "STATUS.json")
    out_FILE = str(tmp_path / "out.json")
    write_json_atomic(out_FILE, {"x": 1})
    write_status(
        status_FILE,
        {"status": "complete", "outputs": {"out.json": "0" * 64}},
    )
    with pytest.raises(ValueError, match=r"^STATUS\.json sha256 does not match output"):
        read_completed_output(status_FILE, out_FILE)


def test_sql_file_not_one_number(tmp_path):
    db_FILE = tmp_path / "t.sqlite"
    conn = sqlite3.connect(str(db_FILE))
    conn.execute("create table t (a int)")
    conn.execute("insert into t values (1), (2)")
    conn.commit()
    sql_FILE = tmp_path / "q.sql"
    sql_FILE.write_text("select a from t\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"^sql file did not return exactly one number"):
        run_sql_file(conn, str(sql_FILE))
    conn.close()


def test_derived_disallowed():
    with pytest.raises(
        ValueError, match=r"^derived expression contains a disallowed character"
    ):
        eval_derived("n_total_pre + unknown_name", {"n_total_pre": 1.0})


def test_n_for_undeclared():
    with pytest.raises(ValueError, match=r"^n_for received an undeclared number name"):
        n_for("not_a_number", {})


def test_attach_agreement_ok():
    df = pd.DataFrame({"n_judgeable": [10, 0], "n_match": [8, 0]})
    out = attach_agreement(df)
    assert out.loc[0, "agreement_status"] == "ok"
    assert out.loc[1, "agreement_status"] == "missing"
    assert pd.isna(out.loc[1, "agreement"])
