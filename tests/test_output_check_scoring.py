"""Score routes: output-check scores prediction files itself.

A model run cannot be replayed in CI, so the gate replays what it can: the
scoring. The references come from an owner-only manifest, the predictions
must cover it exactly, the run card must name a committed script and a pinned
model revision, and the number is recomputed by one normalizer and one edit
distance that the agents never supply. Known answers are written out by hand;
the edit distance is also checked against an independent implementation.
"""

from __future__ import annotations

import json
import random
import sqlite3
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

from tests.test_output_check import CORPUS_SHA, output_check

SHA_A = "a" * 40
SET = "benchmarks/demo"


# --------------------------------------------------------------- normalizer


def test_cer_tokens_drop_punctuation_spaces_and_width():
    got = output_check.score_tokens("我哋今日 去ＳＨＯＰ，ping！", "cer")
    assert got == list("我哋今日去shopping")


def test_traditional_and_simplified_score_the_same():
    trad = output_check.score_tokens("我們說語言，綫同線", "cer")
    simp = output_check.score_tokens("我们说语言线同线", "cer")
    assert trad == simp


def test_cantonese_characters_are_kept_as_they_are():
    assert output_check.score_tokens("佢喺度食咗嘢冇？", "cer") == list("佢喺度食咗嘢冇")


def test_mer_counts_latin_words_whole():
    assert output_check.score_tokens("我哋去 Shopping 啦，don't worry", "mer") == [
        "我", "哋", "去", "shopping", "啦", "don't", "worry"
    ]


def test_punctuation_only_difference_scores_zero():
    ref = output_check.score_tokens("今日天氣好好。", "cer")
    hyp = output_check.score_tokens("今日 天氣，好好！", "cer")
    assert output_check.edit_distance(ref, hyp) == 0


# ------------------------------------------------------------ edit distance


@pytest.mark.parametrize(
    "ref, hyp, want",
    [
        ("abc", "abc", 0),
        ("abc", "abd", 1),  # substitution
        ("abc", "ab", 1),  # deletion
        ("abc", "abcd", 1),  # insertion
        ("abc", "", 3),
        ("", "ab", 2),
        ("kitten", "sitting", 3),
        ("我哋今日去街", "我地今日去街", 1),
    ],
)
def test_edit_distance_known_answers(ref, hyp, want):
    assert output_check.edit_distance(list(ref), list(hyp)) == want


def _reference_distance(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    """A second implementation (memoized recursion) for differential testing."""

    @lru_cache(maxsize=None)
    def d(i: int, j: int) -> int:
        if i == 0:
            return j
        if j == 0:
            return i
        return min(
            d(i - 1, j) + 1,
            d(i, j - 1) + 1,
            d(i - 1, j - 1) + (a[i - 1] != b[j - 1]),
        )

    return d(len(a), len(b))


def test_edit_distance_agrees_with_independent_implementation():
    rng = random.Random(20260923)
    alphabet = list("我哋今日去街ab")
    for _ in range(300):
        a = tuple(rng.choice(alphabet) for _ in range(rng.randint(0, 9)))
        b = tuple(rng.choice(alphabet) for _ in range(rng.randint(0, 9)))
        assert output_check.edit_distance(list(a), list(b)) == _reference_distance(a, b)
        assert output_check.edit_distance(list(a), list(b)) == output_check.edit_distance(
            list(b), list(a)
        )


# ------------------------------------------------------------- score files


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _card(**over) -> dict:
    card = {
        "script_commit": SHA_A,
        "model": "example/asr-small",
        "model_revision": "b" * 40,
        "decoding": {"language": "yue", "beam": 1, "temperature": 0.0},
        "device": "cpu",
        "dirty": False,
    }
    card.update(over)
    return card


def _manifest(root: Path, rows: list[tuple[str, str]] | None = None) -> None:
    rows = rows if rows is not None else [("a", "我哋今日去街"), ("b", "天氣好好")]
    _write_jsonl(root / SET / "manifest.jsonl", [{"id": i, "ref": r} for i, r in rows])


def _pred(root: Path, rel: str, hyps: list[tuple[str, str]], card: dict | None = None) -> Path:
    path = root / rel
    _write_jsonl(path, [{"id": i, "hyp": h} for i, h in hyps])
    if card is not None:
        path.with_name(path.name[: -len(".jsonl")] + ".run.json").write_text(
            json.dumps(card), encoding="utf-8"
        )
    return path


GOOD_HYPS = [("a", "我地今日去街"), ("b", "天氣好好。")]


def test_score_pools_edits_over_the_whole_set(tmp_path):
    _manifest(tmp_path)
    pred = _pred(tmp_path, "tasks/TASK-12/pred/m.jsonl", GOOD_HYPS, _card())
    value, tokens = output_check.ScoreSet(tmp_path, SET, None).score("r", "cer", pred)
    # One substitution over 6 + 4 reference characters, pooled: 1/10, not the
    # average of per-item rates (1/6 + 0/4) / 2.
    assert tokens == 10
    assert value == pytest.approx(100.0)


@pytest.mark.parametrize(
    "hyps, message",
    [
        ([("a", "我哋今日去街")], r"missing 1 \('b'\)"),
        (GOOD_HYPS + [("c", "多出嚟")], r"extra 1 \('c'\)"),
        (GOOD_HYPS + [("a", "重複")], r"repeats id 'a'"),
    ],
)
def test_predictions_must_cover_the_manifest_exactly(tmp_path, hyps, message):
    _manifest(tmp_path)
    pred = _pred(tmp_path, "tasks/TASK-12/pred/m.jsonl", hyps, _card())
    with pytest.raises(output_check.Fail, match=message):
        output_check.ScoreSet(tmp_path, SET, None).score("r", "cer", pred)


def test_empty_reference_fails(tmp_path):
    _manifest(tmp_path, [("a", "我哋今日去街"), ("b", "。。")])
    pred = _pred(tmp_path, "tasks/TASK-12/pred/m.jsonl", GOOD_HYPS, _card())
    with pytest.raises(output_check.Fail, match=r"id 'b' has an empty reference"):
        output_check.ScoreSet(tmp_path, SET, None).score("r", "cer", pred)


@pytest.mark.parametrize(
    "card, message",
    [
        (None, r"m\.run\.json is missing"),
        (_card(model_revision="main"), r"model_revision must be a full 40-character hash"),
        (_card(script_commit="abc123"), r"script_commit must be a full 40-character hash"),
        (_card(dirty=True), r"dirty=True"),
        (_card(decoding={}), r"decoding must be a non-empty object"),
        ({"model": "x"}, r"lacks script_commit, model_revision, decoding, device, dirty"),
    ],
)
def test_run_card_must_pin_script_and_model(tmp_path, card, message):
    _manifest(tmp_path)
    pred = _pred(tmp_path, "tasks/TASK-12/pred/m.jsonl", GOOD_HYPS, card)
    with pytest.raises(output_check.Fail, match=message):
        output_check.ScoreSet(tmp_path, SET, None).score("r", "cer", pred)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_script_commit_must_be_in_the_head_history(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    head = _git(tmp_path, "rev-parse", "HEAD")
    _manifest(tmp_path)
    pred = _pred(tmp_path, "tasks/TASK-12/pred/m.jsonl", GOOD_HYPS, _card(script_commit=SHA_A))
    with pytest.raises(output_check.Fail, match=r"is not a commit in this head's history"):
        output_check.ScoreSet(tmp_path, SET, head).score("r", "cer", pred)
    _pred(tmp_path, "tasks/TASK-12/pred/m.jsonl", GOOD_HYPS, _card(script_commit=head))
    value, _ = output_check.ScoreSet(tmp_path, SET, head).score("r", "cer", pred)
    assert value == pytest.approx(100.0)


# ------------------------------------------------------------------ routes


@pytest.mark.parametrize(
    "name, query, message",
    [
        ("rate_cer_m_pm", "score:wer:tasks/TASK-12/pred/m.jsonl", r"must be score:<cer\|mer>"),
        ("rate_cer_m", "score:cer:tasks/TASK-12/pred/m.jsonl", r"must end in _pm"),
        ("rate_cer_m_pm", "score:cer:tasks/TASK-13/pred/m.jsonl", r"must be tasks/TASK-12/"),
        ("rate_cer_m_pm", "score:cer:tasks/TASK-12/pred/none.jsonl", r"names no file"),
    ],
)
def test_score_route_spelling(tmp_path, name, query, message):
    _pred(tmp_path, "tasks/TASK-12/pred/m.jsonl", GOOD_HYPS)
    with pytest.raises(output_check.Fail, match=message):
        output_check.route("results.json", "12", name, query, tmp_path)


def test_eval_block_must_name_a_benchmarks_set():
    assert output_check.parse_eval_block("b", "```eval\nset benchmarks/demo\n```\n") == SET
    assert output_check.parse_eval_block("b", "no fence") is None
    for body in ("set data/x", "set benchmarks/../x", "set benchmarks/a/b", "sets benchmarks/x"):
        with pytest.raises(output_check.Fail):
            output_check.parse_eval_block("b", f"```eval\n{body}\n```\n")


# --------------------------------------------------------------- full task


def _score_task(
    root: Path,
    *,
    w_value: float = 100.0,
    w_n: int = 10,
    eval_block: bool = True,
    verifier_rel: str = "tasks/TASK-12/mine_pred/m.jsonl",
) -> Path:
    md = root / "tasks" / "TASK-12.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    body = "# TASK-12\n\nstatus: open\n\n```numbers\nrate_cer_m_pm  0.5\n```\n"
    if eval_block:
        body += "\n```eval\nset benchmarks/demo\n```\n"
    md.write_text(body, encoding="utf-8")
    _manifest(root)
    _pred(root, "tasks/TASK-12/pred/m.jsonl", GOOD_HYPS, _card())
    _pred(root, "tasks/TASK-12/mine_pred/m.jsonl", GOOD_HYPS, _card())
    for side, rel, value, n in (
        ("results.json", "tasks/TASK-12/pred/m.jsonl", w_value, w_n),
        ("mine.json", verifier_rel, 100.0, 10),
    ):
        (root / "tasks" / "TASK-12" / side).write_text(
            json.dumps(
                [{"name": "rate_cer_m_pm", "value": value, "n": n, "query": f"score:cer:{rel}"}]
            ),
            encoding="utf-8",
        )
    return md


def _check(root: Path, md: Path) -> list[str]:
    fail: list[str] = []
    conn = sqlite3.connect(":memory:")
    try:
        output_check.check_task(root, md, conn, 60.0, None, None, fail, CORPUS_SHA)
    finally:
        conn.close()
    return fail


def test_score_task_green(tmp_path, capsys):
    md = _score_task(tmp_path)
    assert _check(tmp_path, md) == []
    out = capsys.readouterr().out
    assert "results.json 1 row(s), 1 replayed" in out
    assert "1/1 number(s) agree" in out


def test_written_value_must_match_the_gate_score(tmp_path):
    md = _score_task(tmp_path, w_value=90.0)
    fail = _check(tmp_path, md)
    assert any("written as 90, but its own route gives 100" in f for f in fail), fail


def test_written_n_must_equal_reference_tokens(tmp_path):
    md = _score_task(tmp_path, w_n=2)
    fail = _check(tmp_path, md)
    assert any("n is 2 but cer over the reference set counts 10" in f for f in fail), fail


def test_score_route_without_eval_block_fails(tmp_path):
    md = _score_task(tmp_path, eval_block=False)
    fail = _check(tmp_path, md)
    assert any("a score route needs an ```eval block" in f for f in fail), fail


def test_both_sides_scoring_one_file_fails(tmp_path):
    md = _score_task(tmp_path, verifier_rel="tasks/TASK-12/pred/m.jsonl")
    fail = _check(tmp_path, md)
    assert any("the second run must be its own" in f for f in fail), fail
