"""history_audit treats brief declaration widen/delete as a bar (loop §3.3),
measures task SQL and requires BAR-CHANGE to name bar paths (loop §3.4),
subtracts bar paths from measured so a gate-script fail-site net delete
is not a self-lock (loop §7 item 1 alternative), and moves dead detector
paths into RETIRED instead of deleting them (loop §7 item 2 alternative).
"""

from __future__ import annotations

import importlib.util
import re
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
    assert set(blocks) == {"numbers", "n", "frame", "identities"}
    assert len(blocks["numbers"]) == 41
    assert blocks["identities"] == {
        "n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected": (0.0,),
        "n_judgeable_film_pre + n_judgeable_other_pre + n_judgeable_unassigned_film_pre = n_judgeable_pre": (0.0,),
        "n_judgeable_film_post + n_judgeable_other_post + n_judgeable_unassigned_film_post = n_judgeable_post": (0.0,),
    }
    assert blocks["numbers"]["n_videos_pre"] == (0.0,)
    assert blocks["numbers"]["gap_contract_pp"] == (0.05,)
    # derived: n rows are not numeric, so history_audit skips them; the four
    # video-table constants remain bars.
    assert blocks["n"] == {
        "n_videos_pre": (567.0,),
        "n_videos_post": (567.0,),
        "n_unassigned_period": (567.0,),
        "n_unassigned_film": (567.0,),
    }
    assert blocks["frame"] == {
        "videos_expected": (567.0,),
        "videos_expected_tol": (0.0,),
        "windows_expected": (4911.0,),
        "windows_expected_tol": (0.0,),
        "syllables_expected": (171867.0,),
        "syllables_expected_tol": (0.0,),
        "published_expected": (164693.0,),
        "published_expected_tol": (0.0,),
    }


def test_identical_brief_is_not_a_bar():
    text = BRIEF.read_text(encoding="utf-8")
    assert history_audit.declaration_bars(PATH, text, text) == []


def test_status_only_edit_is_not_a_bar():
    old = BRIEF.read_text(encoding="utf-8")
    new = old.replace("status: closed", "status: open", 1)
    assert "status: open" in new
    assert history_audit.declaration_bars(PATH, old, new) == []


def test_status_blocked_or_escalated_edit_is_not_a_bar():
    old = BRIEF.read_text(encoding="utf-8")
    for st in ("blocked", "escalated"):
        new = old.replace("status: closed", f"status: {st}", 1)
        assert f"status: {st}" in new
        assert history_audit.declaration_bars(PATH, old, new) == []


def test_corpus_sha_stamp_edit_is_not_a_bar():
    """Plan §4.5: the close stamp is not a fenced declaration bar."""
    old = BRIEF.read_text(encoding="utf-8")
    new = re.sub(
        r"^corpus_sha:[ \t]*\S+[ \t]*$",
        "corpus_sha: " + ("a" * 64),
        old,
        count=1,
        flags=re.M,
    )
    assert "a" * 64 in new
    assert new != old
    assert history_audit.declaration_bars(PATH, old, new) == []
    added = old.replace("status: closed\n", "status: closed\ncorpus_sha: " + ("b" * 64) + "\n", 1)
    assert history_audit.declaration_bars(PATH, old, added) == []


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
    assert len(hits) == 41
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


def test_measured_includes_tasks_sql_glob():
    assert "tasks/**/*.sql" in history_audit.MEASURED


def test_task_sql_is_measured_toplevel_sql_still_is():
    m = history_audit.MEASURED
    assert history_audit.match_any("tasks/TASK-6/sql/n_videos_pre.sql", m)
    assert history_audit.match_any("tasks/TASK-6/mine_sql/count_videos_pre.sql", m)
    assert history_audit.match_any("sql/legacy.sql", m)
    assert not history_audit.match_any("tasks/TASK-6.md", m)
    assert not history_audit.match_any("tasks/TASK-6/results.json", m)
    assert not history_audit.match_any("tasks/TASK-6/open_analysis.md", m)


def test_bar_path_from_mutation_count_entry():
    assert history_audit.bar_path("tests/mutations/ (5 -> 4 patches)") == "tests/mutations/"


def test_bar_path_from_yaml_and_brief_entries():
    assert history_audit.bar_path("frame.yaml:threshold (1 -> 2)") == "frame.yaml"
    assert (
        history_audit.bar_path(
            "tasks/TASK-6.md ```numbers gap_contract_pp tolerance widened (0.05 -> 1)"
        )
        == "tasks/TASK-6.md"
    )
    assert history_audit.bar_path("expected/rows.json") == "expected/rows.json"


def test_vague_bar_change_names_no_path():
    bars = ["tests/mutations/ (5 -> 4 patches)"]
    assert history_audit.unnamed_bar_paths(bars, ["BAR-CHANGE: x"]) == [
        "tests/mutations/"
    ]


def test_bar_change_must_name_every_path():
    bars = [
        "tests/mutations/ (5 -> 4 patches)",
        "expected/rows.json",
    ]
    missing = history_audit.unnamed_bar_paths(
        bars, ["BAR-CHANGE: tests/mutations/ fewer patches"]
    )
    assert missing == ["expected/rows.json"]


def test_bar_change_naming_the_patch_covers_mutations_dir():
    bars = ["tests/mutations/ (5 -> 4 patches)"]
    declared = ["BAR-CHANGE: tests/mutations/tier_filter_removed.patch unused"]
    assert history_audit.unnamed_bar_paths(bars, declared) == []


def test_bar_change_naming_all_paths_is_ok():
    bars = [
        "tests/mutations/ (5 -> 4 patches)",
        "expected/rows.json",
    ]
    declared = ["BAR-CHANGE: tests/mutations/ and expected/rows.json unused"]
    assert history_audit.unnamed_bar_paths(bars, declared) == []


def test_scripts_py_is_bar_counted():
    assert "scripts/*.py" in history_audit.BAR_COUNTED
    assert "scripts/**/*.py" in history_audit.BAR_COUNTED
    glob, label = history_audit.BAR_COUNTED["scripts/*.py"]
    assert glob == history_audit.GATE_FAIL_SITE_RE
    assert label == "fail sites"


def test_gate_fail_site_pattern_hits_output_check_not_scope_check():
    pat = history_audit.GATE_FAIL_SITE_RE
    oc = (ROOT / "scripts" / "output_check.py").read_text(encoding="utf-8")
    sc = (ROOT / "scripts" / "scope_check.py").read_text(encoding="utf-8")
    ha = (ROOT / "scripts" / "history_audit.py").read_text(encoding="utf-8")
    n_oc = len(re.findall(pat, oc))
    n_sc = len(re.findall(pat, sc))
    n_ha = len(re.findall(pat, ha))
    assert n_oc > 0
    assert n_sc == 0
    assert n_ha == 0


def test_bar_path_from_gate_fail_site_entry():
    assert (
        history_audit.bar_path("scripts/output_check.py (fail sites 53 -> 51)")
        == "scripts/output_check.py"
    )


def test_gate_dedupe_self_lock_naive_measured_includes_the_bar():
    files = ["scripts/output_check.py"]
    bars = ["scripts/output_check.py (fail sites 53 -> 51)"]
    naive = sorted(f for f in files if history_audit.match_any(f, history_audit.MEASURED))
    assert naive == ["scripts/output_check.py"]
    assert bars and naive


def test_gate_dedupe_measured_paths_subtracts_the_bar():
    files = ["scripts/output_check.py"]
    bars = ["scripts/output_check.py (fail sites 53 -> 51)"]
    assert history_audit.measured_paths(files, bars) == []
    declared = ["BAR-CHANGE: scripts/output_check.py gate dedupe"]
    assert history_audit.unnamed_bar_paths(bars, declared) == []


def test_gate_dedupe_with_src_still_cochanges():
    files = ["scripts/output_check.py", "src/frame.py"]
    bars = ["scripts/output_check.py (fail sites 53 -> 51)"]
    assert history_audit.measured_paths(files, bars) == ["src/frame.py"]


def test_scope_check_is_measured_and_not_a_fail_site_bar_on_this_tree():
    assert history_audit.match_any("scripts/scope_check.py", history_audit.MEASURED)
    files = ["scripts/scope_check.py"]
    bars: list[str] = []
    assert history_audit.measured_paths(files, bars) == ["scripts/scope_check.py"]


PRE_RETIREMENT_SRC = '''\
BAR_FILES = ["expected/*", "expected/**"]
BAR_COUNTED = {
    "scripts/contract_check.py": (r"\\\\b(?:row|compare_check)\\\\s*\\\\(", "contract checks emitted"),
    "scripts/*.py": (r"fail", "fail sites"),
    "scripts/**/*.py": (r"fail", "fail sites"),
    "tests/*.py": (r"match\\\\s*=", "counterexample patterns"),
    "tests/**/*.py": (r"match\\\\s*=", "counterexample patterns"),
}
BAR_YAML_FILES = ["frame.yaml", "rounds/ROUND-*.yaml"]
MUTATION_GLOB = "tests/mutations/*.patch"
MEASURED = ["src/*", "src/**", "sql/*", "sql/**", "data/*", "data/**",
            "scripts/*.py", "scripts/**/*.py", "tasks/**/*.sql"]
'''

RETIRED_TOKENS = frozenset({
    "expected/*",
    "expected/**",
    "scripts/contract_check.py",
    "frame.yaml",
    "rounds/ROUND-*.yaml",
})


def test_retired_convention_markers_are_recognized():
    text = (ROOT / "scripts" / "history_audit.py").read_text(encoding="utf-8")
    block = history_audit.retired_block(text)
    assert block.startswith(history_audit.RETIRED_BEGIN)
    assert block.endswith(history_audit.RETIRED_END)
    for token in RETIRED_TOKENS:
        assert token in block
    assert "scripts/contract_check.py" in history_audit.RETIRED_LOGIC
    assert "expected/*" in history_audit.RETIRED_LOGIC
    assert "frame.yaml" in history_audit.RETIRED_LOGIC


def test_retired_block_empty_when_markers_missing_or_inverted():
    assert history_audit.retired_block("no markers") == ""
    inverted = history_audit.RETIRED_END + "\n" + history_audit.RETIRED_BEGIN
    assert history_audit.retired_block(inverted) == ""


def test_dead_paths_are_retired_not_live():
    live = history_audit.live_detector_paths()
    retired = history_audit.retired_detector_paths()
    assert retired == RETIRED_TOKENS
    assert live.isdisjoint(retired)
    assert "expected/*" not in history_audit.BAR_FILES
    assert "expected/**" not in history_audit.BAR_FILES
    assert "scripts/gate_config.json" in history_audit.BAR_FILES
    for g in ("scripts/*", "scripts/**", ".github/*", ".github/**", "tests/mutations/**", "tests/fixtures/**"):
        assert g in history_audit.BAR_FILES
    assert "scripts/contract_check.py" not in history_audit.BAR_COUNTED
    assert history_audit.BAR_YAML_FILES == []
    assert "sql/*" in history_audit.MEASURED
    assert "sql/**" in history_audit.MEASURED
    assert "tasks/**/*.sql" in history_audit.MEASURED


def test_source_inventory_equals_live_union_retired():
    text = (ROOT / "scripts" / "history_audit.py").read_text(encoding="utf-8")
    inv = history_audit.detector_inventory(text)
    assert inv == history_audit.live_detector_paths() | history_audit.retired_detector_paths()
    assert RETIRED_TOKENS <= inv
    assert "tasks/**/*.sql" in inv
    assert "sql/*" in inv


def test_inventory_does_not_count_regex_values_or_labels():
    src = (
        "BAR_COUNTED = {\n"
        '    "scripts/contract_check.py": (r"\\\\b(?:row|compare_check)\\\\s*\\\\(", '
        '"contract checks emitted"),\n'
        "}\n"
        "RETIRED = {\n"
        '    "BAR_COUNTED": {\n'
        '        "scripts/contract_check.py": (r"not-a-path", "contract checks emitted"),\n'
        "    },\n"
        "}\n"
    )
    inv = history_audit.detector_inventory(src)
    assert inv == frozenset({"scripts/contract_check.py"})
    assert "contract checks emitted" not in inv
    assert "not-a-path" not in inv


def test_retirement_preserves_inventory_versus_pre_retirement_source():
    """Moving dead globs into RETIRED must not drop them from the union."""
    old = history_audit.detector_inventory(PRE_RETIREMENT_SRC)
    new = history_audit.detector_inventory(
        (ROOT / "scripts" / "history_audit.py").read_text(encoding="utf-8")
    )
    assert RETIRED_TOKENS <= old
    assert RETIRED_TOKENS <= new
    lost = old - new
    assert lost == frozenset()


def test_delete_retired_detector_without_convention_shrinks_inventory():
    """The withdrawn original: delete the glob and do not keep it in RETIRED."""
    text = (ROOT / "scripts" / "history_audit.py").read_text(encoding="utf-8")
    full = history_audit.detector_inventory(text)
    assert "expected/*" in full
    stripped = text.replace('"expected/*", ', "").replace('"expected/*"', "")
    stripped = stripped.replace("'expected/*', ", "").replace("'expected/*'", "")
    shrunk = history_audit.detector_inventory(stripped)
    assert "expected/*" not in shrunk
    assert len(shrunk) < len(full)
    assert "expected/*" in (full - shrunk)


def test_delete_whole_retired_dict_shrinks_inventory():
    src_with = (
        "BAR_FILES = []\n"
        "BAR_COUNTED = {'scripts/*.py': (r'x', 'fail sites')}\n"
        "BAR_YAML_FILES = []\n"
        'MUTATION_GLOB = "tests/mutations/*.patch"\n'
        'MEASURED = ["src/*"]\n'
        "RETIRED = {\n"
        '    "BAR_FILES": ["expected/*", "expected/**"],\n'
        '    "BAR_COUNTED": {"scripts/contract_check.py": (r"row", "x")},\n'
        '    "BAR_YAML_FILES": ["frame.yaml", "rounds/ROUND-*.yaml"],\n'
        "}\n"
    )
    src_without = (
        "BAR_FILES = []\n"
        "BAR_COUNTED = {'scripts/*.py': (r'x', 'fail sites')}\n"
        "BAR_YAML_FILES = []\n"
        'MUTATION_GLOB = "tests/mutations/*.patch"\n'
        'MEASURED = ["src/*"]\n'
    )
    was = history_audit.detector_inventory(src_with)
    now = history_audit.detector_inventory(src_without)
    assert RETIRED_TOKENS <= was
    assert was - now == RETIRED_TOKENS


def test_bar_path_from_detector_inventory_entry():
    assert (
        history_audit.bar_path(
            "scripts/history_audit.py (detector inventory 20 -> 19; lost expected/*)"
        )
        == "scripts/history_audit.py"
    )


def test_yaml_bar_helper_is_preserved_alongside_retired_paths():
    """Retirement keeps yaml_bar_keys_touched; only the file globs moved."""
    assert callable(history_audit.yaml_bar_keys_touched)
    assert history_audit.BAR_YAML_KEYS.search("expected_rows: 164693")



def test_adding_outside_frame_name_is_a_bar_removing_is_not():
    old = NUMBERS + "```outside_frame\nrare_share_pre\n```\n"
    new = NUMBERS + "```outside_frame\nrare_share_pre  # cutoff\nrare_share_post\n```\n"
    hits = history_audit.declaration_bars(PATH, old, new)
    assert hits == [
        "tasks/TASK-6.md ```outside_frame rare_share_post added "
        "(exempt from the exclude invariant)"
    ]
    assert history_audit.declaration_bars(PATH, new, old) == []
    assert history_audit.declaration_bars(PATH, new, new) == []


def test_adding_outside_frame_block_to_existing_brief_is_a_bar():
    new = NUMBERS + "```outside_frame\nn_all\n```\n"
    hits = history_audit.declaration_bars(PATH, NUMBERS, new)
    assert hits == [
        "tasks/TASK-6.md ```outside_frame n_all added (exempt from the exclude invariant)"
    ]


def test_gate_config_is_a_bar_file():
    assert "scripts/gate_config.json" in history_audit.BAR_FILES


# --------------------------------------------------------------------------- identities lines and gate files are bars

IDENT = NUMBERS + "```identities\na + b = c  0\nx = y * 2  0.05\n```\n"


def test_identity_line_deleted_or_reworded_is_a_bar():
    gone = NUMBERS + "```identities\nx = y * 2  0.05\n```\n"
    assert history_audit.declaration_bars(PATH, IDENT, gone) == [
        "tasks/TASK-6.md ```identities a + b = c deleted"
    ]
    reworded = NUMBERS + "```identities\na + b = d  0\nx = y * 2  0.05\n```\n"
    assert history_audit.declaration_bars(PATH, IDENT, reworded) == [
        "tasks/TASK-6.md ```identities a + b = c deleted"
    ]
    assert history_audit.declaration_bars(PATH, NUMBERS, IDENT) == []  # adding is not a bar


def test_identity_tolerance_widened_is_a_bar_tightened_is_not():
    wider = NUMBERS + "```identities\na + b = c  0.1\nx = y * 2  0.05\n```\n"
    assert history_audit.declaration_bars(PATH, IDENT, wider) == [
        "tasks/TASK-6.md ```identities a + b = c tolerance widened (0 -> 0.1)"
    ]
    tighter = NUMBERS + "```identities\na + b = c  0\nx = y * 2  0.01\n```\n"
    assert history_audit.declaration_bars(PATH, IDENT, tighter) == []
    spaced = NUMBERS + "```identities\na   +  b =  c   0\nx = y * 2  0.05\n```\n"
    assert history_audit.declaration_bars(PATH, IDENT, spaced) == []


def test_identities_block_deleted_is_a_bar():
    assert history_audit.declaration_bars(PATH, IDENT, NUMBERS) == [
        "tasks/TASK-6.md ```identities block deleted"
    ]


def test_gate_and_ci_files_are_bar_paths():
    for f in (
        "scripts/output_check.py", "scripts/relations.py", "scripts/verify.py",
        ".github/workflows/ci.yml", ".github/CODEOWNERS",
        "tests/test_output_check.py", "tests/test_relations.py", "tests/test_scope_check.py",
        "tests/test_history_audit.py", "tests/mutations/x.patch", "tests/fixtures/relations_probe/n_count.sql",
    ):
        assert history_audit.match_any(f, history_audit.BAR_FILES), f
    for f in ("tests/test_src_sql_literals.py", "tasks/TASK-9/sql/x.sql", "LOOP.md", "src/tables.py"):
        assert not history_audit.match_any(f, history_audit.BAR_FILES), f


# --- frame predicates, eval lines, and the gate-review line ------------------

import subprocess
import sys


def test_frame_predicate_change_is_a_bar_move():
    old = NUMBERS + "```frame\nwindows.tier IN ('A','B')\npublished_expected 164693\n```\n"
    new = NUMBERS + "```frame\nwindows.tier IN ('A','B','C')\npublished_expected 164693\n```\n"
    hits = history_audit.declaration_bars(PATH, old, new)
    assert hits == [
        "tasks/TASK-6.md ```frame predicate \"windows.tier IN ('A','B')\" changed or deleted"
    ]
    assert history_audit.declaration_bars(PATH, old, old) == []


def test_eval_line_change_and_block_deletion_are_bar_moves():
    old = NUMBERS + "```eval\nset benchmarks/demo\n```\n"
    new = NUMBERS + "```eval\nset benchmarks/easier\n```\n"
    assert history_audit.declaration_bars(PATH, old, new) == [
        "tasks/TASK-6.md ```eval 'set benchmarks/demo' changed or deleted"
    ]
    assert history_audit.declaration_bars(PATH, old, NUMBERS) == [
        "tasks/TASK-6.md ```eval block deleted"
    ]
    assert history_audit.declaration_bars(PATH, NUMBERS, old) == []


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _gate_change_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    _git(tmp_path, "init", "-q", str(repo))
    (repo / "scripts" / "gate.py").write_text("def check():\n    raise Fail('x')\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "scripts" / "gate.py").write_text(
        "def check():\n    raise Fail('x')\n    raise Fail('y')\n", encoding="utf-8"
    )
    _git(repo, "commit", "-q", "-am", "head")
    return repo, base


def _audit(repo: Path, base: str, body: str, monkeypatch, capsys) -> tuple[int, str]:
    body_file = repo.parent / "body.txt"
    body_file.write_text(body, encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        sys, "argv", ["history_audit.py", "--base", base, "--pr-body-file", str(body_file)]
    )
    code = history_audit.main()
    return code, capsys.readouterr().out


def test_gate_change_needs_a_gate_review_line(tmp_path, monkeypatch, capsys):
    repo, base = _gate_change_repo(tmp_path)
    code, out = _audit(
        repo, base, "BAR-CHANGE: scripts/gate.py -- one more check\n", monkeypatch, capsys
    )
    assert code == 1, out
    assert "a gate file changed (scripts/gate.py); the pull-request body needs 'Gate-review:" in out
    assert "there is no such line" in out


def test_gate_review_must_name_the_current_head(tmp_path, monkeypatch, capsys):
    repo, base = _gate_change_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    code, out = _audit(
        repo,
        base,
        f"BAR-CHANGE: scripts/gate.py -- one more check\nGate-review: {base[:12]} fresh session\n",
        monkeypatch,
        capsys,
    )
    assert code == 1, out
    assert "no line names the current head commit" in out
    code, out = _audit(
        repo,
        base,
        f"BAR-CHANGE: scripts/gate.py -- one more check\nGate-review: {head[:12]} fresh Claude session, 2026-09-23\n",
        monkeypatch,
        capsys,
    )
    assert code == 0, out
    assert f"gate review: Gate-review: {head[:12]} fresh Claude session, 2026-09-23" in out


def test_renamed_gate_file_is_a_bar_and_needs_review(tmp_path, monkeypatch, capsys):
    """A rename is a delete plus an add, so the old path cannot hide."""
    repo, base = _gate_change_repo(tmp_path)
    _git(repo, "mv", "scripts/gate.py", "scripts/gate2.py")
    _git(repo, "commit", "-q", "-m", "rename")
    code, out = _audit(repo, base, "", monkeypatch, capsys)
    assert code == 1, out
    assert "scripts/gate.py" in out
    assert "no 'BAR-CHANGE: <reason>' line" in out


def test_added_file_that_could_shadow_a_module_needs_review(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    _git(tmp_path, "init", "-q", str(repo))
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "scripts" / "json.py").write_text("loads = None\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add")
    code, out = _audit(repo, base, "", monkeypatch, capsys)
    assert code == 1, out
    assert "a gate file changed (scripts/json.py)" in out


# ------------------------------------------------ one fence parser for all gates

SWALLOW = """# TASK-6
status: closed

```fixture
```numbers
# name                     tol
n_videos_pre               0
gap_contract_pp            5.0
agree_film_pre             0.0005
rate_tone_pre_pm           0.5
```

```numbers
# name                     tol
n_videos_pre               0
gap_contract_pp            0.05
agree_film_pre             0.0005
rate_tone_pre_pm           0.5
```
"""


def test_audit_reads_the_numbers_block_the_gate_applies():
    """A fixture opener must not hide the real numbers block behind a decoy."""
    applied = history_audit.output_check.BLOCK.search(SWALLOW).group(1)
    assert "gap_contract_pp            5.0" in applied
    blocks = history_audit.parse_declaration_blocks(SWALLOW)
    assert blocks["numbers"]["gap_contract_pp"] == (5.0,)


def test_fence_swallow_is_a_widening_and_an_ambiguity():
    hits = history_audit.declaration_bars(PATH, NUMBERS, SWALLOW)
    assert f"{PATH} ```numbers gap_contract_pp tolerance widened (0.05 -> 5)" in hits, hits
    assert any("declaration fences made ambiguous" in h and "opens inside" in h for h in hits), hits


def test_fence_layout_of_real_briefs_is_clean():
    for md in sorted((ROOT / "tasks").glob("TASK-*.md")):
        assert history_audit.output_check.fence_layout_errors(md.name, md.read_text(encoding="utf-8")) == []


# ------------------------------------------------ files that steer the gate tests

def _tests_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(tmp_path, "init", "-q", str(repo))
    (repo / "tests" / "test_fork.py").write_text(
        "from tests.test_output_check import output_check\n\ndef test_x():\n    assert output_check\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_sql.py").write_text(
        "from src.hashing import verify_corpus_hash\n\ndef test_y():\n    assert verify_corpus_hash\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_conftest_that_skips_gate_tests_needs_review(tmp_path, monkeypatch, capsys):
    repo, base = _tests_repo(tmp_path)
    (repo / "tests" / "conftest.py").write_text(
        'collect_ignore_glob = ["test_output_check*.py", "test_fork.py"]\n', encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "conftest")
    code, out = _audit(repo, base, "", monkeypatch, capsys)
    assert code == 1, out
    assert "a gate file changed (tests/conftest.py)" in out


def test_deleting_a_test_that_imports_a_gate_test_is_a_bar(tmp_path, monkeypatch, capsys):
    repo, base = _tests_repo(tmp_path)
    _git(repo, "rm", "-q", "tests/test_fork.py")
    _git(repo, "commit", "-q", "-m", "drop")
    code, out = _audit(repo, base, "", monkeypatch, capsys)
    assert code == 1, out
    assert "bars touched:     ['tests/test_fork.py']" in out
    assert "a gate file changed (tests/test_fork.py)" in out


def test_worker_test_of_src_is_not_a_gate_file(tmp_path, monkeypatch, capsys):
    repo, base = _tests_repo(tmp_path)
    (repo / "tests" / "test_sql.py").write_text(
        "from src.hashing import verify_corpus_hash\n\ndef test_y():\n    assert callable(verify_corpus_hash)\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_frame.py").write_text(
        "from src.frame import load_published_frame\n\ndef test_z():\n    assert load_published_frame\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "worker tests")
    code, out = _audit(repo, base, "", monkeypatch, capsys)
    assert code == 0, out
    assert "history_audit: PASS" in out


def test_new_test_reaching_a_gate_dynamically_needs_review(tmp_path, monkeypatch, capsys):
    repo, base = _tests_repo(tmp_path)
    (repo / "tests" / "test_zz.py").write_text(
        'import importlib\nm = importlib.import_module("tests.test_" + "output_check")\n',
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "sneaky")
    code, out = _audit(repo, base, "", monkeypatch, capsys)
    assert code == 1, out
    assert "a gate file changed (tests/test_zz.py)" in out


def test_pytest_configuration_files_are_gate_files():
    for f in ["conftest.py", "tests/conftest.py", "tests/sub/conftest.py", "tests/__init__.py",
              "tests/sub/__init__.py", "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini",
              "requirements.txt", "requirements-dev.txt"]:
        assert history_audit.match_any(f, history_audit.BAR_FILES), f
    for f in ["src/__init__.py", "tasks/TASK-9/requirements.md"]:
        assert not history_audit.match_any(f, history_audit.BAR_FILES), f
