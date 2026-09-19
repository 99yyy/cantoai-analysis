"""history_audit treats brief declaration widen/delete as a bar (loop §3.3)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "history_audit", ROOT / "scripts" / "history_audit.py"
)
assert SPEC is not None and SPEC.loader is not None
history_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(history_audit)

BRIEF = ROOT / "tasks" / "TASK-6.md"
PATH = "tasks/TASK-6.md"

NUMBERS = """# TASK-6
status: closed

```numbers
# name                     tol
n_videos_pre               0
gap_contract_pp            0.05
agree_film_pre             0.0005
rate_tone_pre_pm           0.5
```
"""


def test_task_brief_regex_is_top_level_only():
    assert history_audit.TASK_BRIEF_RE.match("tasks/TASK-6.md")
    assert history_audit.TASK_BRIEF_RE.match("tasks/TASK-12.md")
    assert not history_audit.TASK_BRIEF_RE.match("tasks/TASK-6/open_analysis.md")
    assert not history_audit.TASK_BRIEF_RE.match("tasks/NOTES.md")


def test_real_task_6_numbers_block_has_39_names():
    blocks = history_audit.parse_declaration_blocks(BRIEF.read_text(encoding="utf-8"))
    assert set(blocks) == {"numbers"}
    assert len(blocks["numbers"]) == 39
    assert blocks["numbers"]["n_videos_pre"] == (0.0,)
    assert blocks["numbers"]["gap_contract_pp"] == (0.05,)


def test_identical_brief_is_not_a_bar():
    text = BRIEF.read_text(encoding="utf-8")
    assert history_audit.declaration_bars(PATH, text, text) == []


def test_status_only_edit_is_not_a_bar():
    old = BRIEF.read_text(encoding="utf-8")
    new = old.replace("status: closed", "status: open", 1)
    assert "status: open" in new
    assert history_audit.declaration_bars(PATH, old, new) == []


def test_widening_a_numbers_tolerance_is_a_bar():
    new = NUMBERS.replace("gap_contract_pp            0.05", "gap_contract_pp            1000000")
    hits = history_audit.declaration_bars(PATH, NUMBERS, new)
    assert hits == [
        "tasks/TASK-6.md ```numbers gap_contract_pp tolerance widened (0.05 -> 1000000)"
    ]


def test_widening_all_numbers_tolerances_is_a_bar():
    old = BRIEF.read_text(encoding="utf-8")
    lines = []
    in_block = False
    for line in old.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```numbers"):
            in_block = True
            lines.append(line)
            continue
        if in_block and stripped == "```":
            in_block = False
            lines.append(line)
            continue
        if in_block:
            body = line.split("#", 1)[0].strip()
            parts = body.split()
            if len(parts) == 2:
                line = f"{parts[0]} 1000000\n" if line.endswith("\n") else f"{parts[0]} 1000000"
        lines.append(line)
    new = "".join(lines)
    hits = history_audit.declaration_bars(PATH, old, new)
    assert len(hits) == 39
    assert all("tolerance widened" in h and "```numbers" in h for h in hits)
    assert any("n_videos_pre tolerance widened (0 -> 1000000)" in h for h in hits)


def test_tightening_a_numbers_tolerance_is_not_a_bar():
    new = NUMBERS.replace("gap_contract_pp            0.05", "gap_contract_pp            0.01")
    assert history_audit.declaration_bars(PATH, NUMBERS, new) == []


def test_deleting_a_numbers_name_is_a_bar():
    new = NUMBERS.replace("n_videos_pre               0\n", "")
    hits = history_audit.declaration_bars(PATH, NUMBERS, new)
    assert hits == ["tasks/TASK-6.md ```numbers n_videos_pre deleted"]


def test_deleting_the_numbers_block_is_a_bar():
    new = NUMBERS.replace(
        "```numbers\n# name                     tol\n"
        "n_videos_pre               0\n"
        "gap_contract_pp            0.05\n"
        "agree_film_pre             0.0005\n"
        "rate_tone_pre_pm           0.5\n"
        "```\n",
        "",
    )
    hits = history_audit.declaration_bars(PATH, NUMBERS, new)
    assert hits == ["tasks/TASK-6.md ```numbers block deleted"]


def test_adding_a_numbers_name_is_not_a_bar():
    new = NUMBERS.replace(
        "rate_tone_pre_pm           0.5\n",
        "rate_tone_pre_pm           0.5\nn_extra                    0\n",
    )
    assert history_audit.declaration_bars(PATH, NUMBERS, new) == []


def test_adding_fixture_frame_n_blocks_is_not_a_bar():
    new = NUMBERS + """
```fixture
n_videos_pre 391
```

```frame
windows.tier IN ('A','B')
expected_rows 164693
expected_rows_tol 0
```

```n
n_videos_pre 567
```
"""
    assert history_audit.declaration_bars(PATH, NUMBERS, new) == []


def test_changing_a_fixture_expected_value_is_a_bar():
    old = NUMBERS + "```fixture\nn_videos_pre 391\n```\n"
    new = NUMBERS + "```fixture\nn_videos_pre 1\n```\n"
    hits = history_audit.declaration_bars(PATH, old, new)
    assert hits == ["tasks/TASK-6.md ```fixture n_videos_pre (391 -> 1)"]


def test_deleting_a_fixture_name_is_a_bar():
    old = NUMBERS + "```fixture\nn_videos_pre 391\nagree_film_pre 0.9\n```\n"
    new = NUMBERS + "```fixture\nagree_film_pre 0.9\n```\n"
    hits = history_audit.declaration_bars(PATH, old, new)
    assert hits == ["tasks/TASK-6.md ```fixture n_videos_pre deleted"]


def test_deleting_a_fixture_block_is_a_bar():
    old = NUMBERS + "```fixture\nn_videos_pre 391\n```\n"
    hits = history_audit.declaration_bars(PATH, old, NUMBERS)
    assert hits == ["tasks/TASK-6.md ```fixture block deleted"]


def test_frame_predicate_lines_are_not_entries():
    text = NUMBERS + (
        "```frame\n"
        "windows.tier IN ('A','B')\n"
        "expected_rows 164693\n"
        "expected_rows_tol 0\n"
        "```\n"
    )
    blocks = history_audit.parse_declaration_blocks(text)
    assert blocks["frame"] == {
        "expected_rows": (164693.0,),
        "expected_rows_tol": (0.0,),
    }


def test_widening_frame_tolerance_is_a_bar():
    old = NUMBERS + "```frame\nexpected_rows_tol 0\n```\n"
    new = NUMBERS + "```frame\nexpected_rows_tol 10\n```\n"
    hits = history_audit.declaration_bars(PATH, old, new)
    assert hits == [
        "tasks/TASK-6.md ```frame expected_rows_tol tolerance widened (0 -> 10)"
    ]


def test_tightening_frame_tolerance_is_not_a_bar():
    old = NUMBERS + "```frame\nexpected_rows_tol 10\n```\n"
    new = NUMBERS + "```frame\nexpected_rows_tol 0\n```\n"
    assert history_audit.declaration_bars(PATH, old, new) == []


def test_changing_frame_expected_rows_is_a_bar():
    old = NUMBERS + "```frame\nexpected_rows 164693\n```\n"
    new = NUMBERS + "```frame\nexpected_rows 1\n```\n"
    hits = history_audit.declaration_bars(PATH, old, new)
    assert hits == ["tasks/TASK-6.md ```frame expected_rows (164693 -> 1)"]


def test_changing_n_block_expected_value_is_a_bar():
    old = NUMBERS + "```n\nn_videos_pre 567\n```\n"
    new = NUMBERS + "```n\nn_videos_pre 1\n```\n"
    hits = history_audit.declaration_bars(PATH, old, new)
    assert hits == ["tasks/TASK-6.md ```n n_videos_pre (567 -> 1)"]


def test_deleting_n_block_is_a_bar():
    old = NUMBERS + "```n\nn_videos_pre 567\n```\n"
    hits = history_audit.declaration_bars(PATH, old, NUMBERS)
    assert hits == ["tasks/TASK-6.md ```n block deleted"]


def test_emptying_a_numbers_block_deletes_each_name():
    new = """# TASK-6
status: closed

```numbers
```
"""
    hits = history_audit.declaration_bars(PATH, NUMBERS, new)
    assert "tasks/TASK-6.md ```numbers n_videos_pre deleted" in hits
    assert "tasks/TASK-6.md ```numbers gap_contract_pp deleted" in hits
    assert len(hits) == 4
