"""Every src assertion message has a pytest.raises match=^... counterexample."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.agreement import row_measures, status_for_measure
from src.compare import (
    assert_no_clap_in_comparison,
    bh_corrected,
    difference_vs_baseline,
    exploratory_row,
    require_ci_unreliable,
    require_comparison_id,
    require_inconclusive,
)
from src.flatten import SEP, flatten
from src.frame import apply_boiler_exclusion, apply_tier_whitelist, assert_stratum_column, assign_group
from src.manifest import assert_git_clean, parse_upload_date
from src.merge import checked_merge
from src.onset import parse_onset
from src.paths import load_complete_output, refuse_inference, require_path
from src.round3 import _counts, _prepare_base, require_stratum_count
from src.seeds import assert_stratum_seeds, stratum_seed
from src.sql_loader import load_sql
from src.weights import stratum_weights

ROOT = Path(__file__).resolve().parents[1]


def test_load_sql_missing():
    with pytest.raises(FileNotFoundError, match=r"^load_sql cannot locate SQL file"):
        load_sql("no_such_query", str(ROOT / "sql"))


def test_path_bearing_no_default():
    with pytest.raises(ValueError, match=r"^path-bearing argument has no default"):
        require_path("corpus_PATH", None)


def test_status_not_complete(tmp_path: Path):
    out = tmp_path / "out.json"
    out.write_text("{}", encoding="utf-8")
    status = tmp_path / "STATUS.json"
    status.write_text(json.dumps({"status": "running"}), encoding="utf-8")
    with pytest.raises(ValueError, match=r"^STATUS.json is not complete or sha256 mismatch"):
        load_complete_output(out, status)


def test_inference_barred():
    with pytest.raises(ValueError, match=r"^inference entry points are barred this round"):
        refuse_inference(["run_clap_sing.py"])


def test_join_keys_mismatch():
    frame = {"joins": {"j": {"keys": ["uid"], "expected_rows": 99}}}
    left = pd.DataFrame({"uid": [1, 2], "a": [1, 1]})
    right = pd.DataFrame({"uid": [1, 2], "b": [2, 2]})
    with pytest.raises(
        ValueError, match=r"^checked_merge join keys do not match frame.yaml joins"
    ):
        checked_merge(left, right, "j", frame)


def test_join_name_missing():
    left = pd.DataFrame({"uid": [1], "a": [1]})
    right = pd.DataFrame({"uid": [1], "b": [1]})
    with pytest.raises(ValueError, match=r"^join_name missing from frame.yaml joins"):
        checked_merge(left, right, "absent", {"joins": {}})


def test_duplicate_output_column():
    frame = {"joins": {"j": {"keys": ["uid"], "expected_rows": 1}}}
    left = pd.DataFrame({"uid": [1], "x": [1]})
    right = pd.DataFrame({"uid": [1], "x": [2]})
    with pytest.raises(ValueError, match=r"^duplicate output column or key"):
        checked_merge(left, right, "j", frame)


def test_tier_whitelist_missing():
    with pytest.raises(
        ValueError, match=r"^tier whitelist predicate missing from published-set filter"
    ):
        apply_tier_whitelist(
            pd.DataFrame({"video_id": ["v"]}),
            {"tier_whitelist": ["A", "B"]},
            [],
        )


def test_barred_stratifier():
    frame = {
        "barred_stratifiers": ["flag_sing"],
        "groups": {
            "treatment": {"predicate": "film_flag = 1"},
            "control": {"predicate": "contemporary_only = 1"},
        },
    }
    with pytest.raises(ValueError, match=r"^barred stratifier used as group or stratum"):
        assert_stratum_column("flag_sing", frame)


def test_both_groups():
    with pytest.raises(ValueError, match=r"^row matches both treatment and control"):
        assign_group(1, 1)


def test_accounting_required():
    with pytest.raises(
        ValueError, match=r"^rows dropped must be recorded in row_accounting"
    ):
        apply_boiler_exclusion(pd.DataFrame({"uid": ["w"]}), [])


def test_null_jp_match_judgeable():
    with pytest.raises(ValueError, match=r"^NULL jp_match on judgeable row"):
        row_measures(
            {
                "jp_match": None,
                "jp_realized": "aa1",
                "dur": 0.2,
                "singing_prob": 0.1,
                "snr_db": 12.0,
            }
        )


def test_status_ok_requires_data():
    with pytest.raises(
        ValueError, match=r"^status ok requires non-null measure computed from data"
    ):
        status_for_measure(0, computed_from_data=False)


def test_stratum_seed_construction():
    with pytest.raises(
        ValueError,
        match=r"^per-stratum seed must equal int\(sha256\(master_seed:h\)\[:8\], 16\)",
    ):
        assert_stratum_seeds(20260918, {"A": 20260918})


def test_stratum_seeds_distinct():
    with pytest.raises(ValueError, match=r"^per-stratum seeds must be pairwise distinct"):
        assert_stratum_seeds(1, {"A": 1, "B": 1})


def test_unweighted_mean():
    with pytest.raises(ValueError, match=r"^unweighted mean across strata is forbidden"):
        stratum_weights([10.0], [0.0])


def test_difference_needs_components():
    with pytest.raises(
        ValueError, match=r"^reported difference must include group and baseline values"
    ):
        difference_vs_baseline(0.1, None, 0.2, 0.3)


def test_comparison_id_missing():
    with pytest.raises(ValueError, match=r"^comparison_id missing from declared comparisons"):
        require_comparison_id("nope", ["c1_period_drop"])


def test_exploratory_has_pvalue():
    with pytest.raises(ValueError, match=r"^exploratory row must not carry a p-value"):
        exploratory_row({"exploratory": 1, "p_raw": 0.01, "p_bh": None})


def test_min_judgeable_inconclusive():
    with pytest.raises(
        ValueError,
        match=r"^n_h_judgeable below min_judgeable requires conclusion inconclusive",
    ):
        require_inconclusive(10, 200, "pending")


def test_ci_unreliable():
    with pytest.raises(ValueError, match=r"^G_h below 10 requires ci_unreliable=1"):
        require_ci_unreliable(3, 0)


def test_clap_join_barred():
    with pytest.raises(
        ValueError,
        match=r"^clap_sing must not join PANNs singing_prob in the same comparison",
    ):
        assert_no_clap_in_comparison("c2_highsnr_onset_residual", ["uid", "clap_sing"])


def test_onset_missing():
    with pytest.raises(ValueError, match=r"^onset missing from jp_default"):
        parse_onset(None)


def test_flatten_separator():
    with pytest.raises(
        ValueError, match=r"^flatten separator must not occur inside a key segment"
    ):
        flatten({f"a{SEP}b": 1})


def test_git_dirty_rejected():
    with pytest.raises(ValueError, match=r"^git_dirty true is rejected"):
        assert_git_clean(True)


def test_upload_date_missing():
    with pytest.raises(ValueError, match=r"^upload_date missing"):
        parse_upload_date(None)


def test_bh_m_mismatch():
    with pytest.raises(ValueError, match=r"^comparison_id missing from declared comparisons"):
        bh_corrected([0.1, 0.2], 3)


def test_checked_merge_happy():
    frame = {"joins": {"j": {"keys": ["uid"], "expected_rows": 2}}}
    left = pd.DataFrame({"uid": [1, 2], "a": [1, 1]})
    right = pd.DataFrame({"uid": [1, 2], "b": [2, 2]})
    out = checked_merge(left, right, "j", frame)
    assert len(out) == 2


def test_tier_whitelist_happy():
    df = pd.DataFrame({"tier": ["A", "C", "B"]})
    out = apply_tier_whitelist(df, {"tier_whitelist": ["A", "B"]}, [])
    assert list(out["tier"]) == ["A", "B"]


def test_stratum_seed_happy():
    master = 20260918
    seeds = {"A": stratum_seed(master, "A"), "B": stratum_seed(master, "B")}
    assert_stratum_seeds(master, seeds)


def test_weights_happy():
    assert stratum_weights([10.0, 20.0], [2.0, 4.0]) == [5.0, 5.0]


def test_status_ok_from_data():
    assert status_for_measure(0.5, computed_from_data=True) == "ok"


def test_n_judgeable_identity_failed():
    df = pd.DataFrame(
        {
            "_empty": [False],
            "_dur_le_0": [False],
            "_judgeable": [False],
            "_match": [False],
        }
    )
    with pytest.raises(ValueError, match=r"^n_judgeable identity failed"):
        _counts(df)


def test_window_quality_required():
    df = pd.DataFrame(
        {
            "syllable_dur": [0.2],
            "jp_realized": ["aa1"],
            "jp_match": ["exact_default"],
            "video_id": ["v1"],
            "upload_date": ["20240101"],
        }
    )
    flags = pd.DataFrame(
        {
            "video_id": ["v1"],
            "film_flag": [1],
            "contemporary_only": [0],
        }
    )
    with pytest.raises(ValueError, match=r"^window quality required"):
        _prepare_base(df, flags, None, need_quality=True, row_accounting=[])


def test_manifest_stratum_count_none():
    with pytest.raises(ValueError, match=r"^manifest stratum count is None"):
        require_stratum_count(None)
