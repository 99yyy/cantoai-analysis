"""SYNTHETIC FIXTURES ONLY. No audio, human gold, ASR predictions, or real results."""
import itertools
import json
from pathlib import Path
import tempfile
import unittest
import evaluate as ev


class MetricTests(unittest.TestCase):
    def test_substitution(self):
        self.assertEqual(ev.edit_counts("甲乙", "甲丙"), {"N": 2, "S": 1, "D": 0, "I": 0, "E": 1})

    def test_deletion(self):
        self.assertEqual(ev.edit_counts("甲乙", "甲"), {"N": 2, "S": 0, "D": 1, "I": 0, "E": 1})

    def test_insertion(self):
        self.assertEqual(ev.edit_counts("甲", "甲乙"), {"N": 1, "S": 0, "D": 0, "I": 1, "E": 1})

    def test_empty_reference(self):
        self.assertEqual(ev.edit_counts("", "abc")["I"], 3)

    def test_empty_hypothesis(self):
        self.assertEqual(ev.edit_counts("abc", "")["D"], 3)
        self.assertEqual(ev.edit_counts("", "")["E"], 0)

    def test_unicode_line_endings(self):
        self.assertEqual(ev.normalize("e\u0301\r\n甲\r乙"), "é\n甲\n乙")
        self.assertEqual(ev.edit_counts(ev.normalize("e\u0301"), ev.normalize("é"))["E"], 0)

    def test_no_cantonese_mapping_or_casefold(self):
        self.assertEqual(ev.normalize("系係ABCabc0123"), "系係ABCabc0123")
        self.assertEqual(ev.edit_counts("系", "係")["S"], 1)
        self.assertEqual(ev.edit_counts("A", "a")["S"], 1)

    def test_punctuation_whitespace_only(self):
        self.assertEqual(ev.normalize("你，好！ A1\t+\n$é", True), "你好A1+$é")
        self.assertEqual(ev.normalize("你，好！ A1\t+\n$é"), "你，好！ A1\t+\n$é")

    def test_deterministic_tie(self):
        self.assertEqual(ev.edit_counts("ab", "ba"), {"N": 2, "S": 2, "D": 0, "I": 0, "E": 2})

    def test_exhaustive_short_distance_and_count_invariants(self):
        # Independent recursive distance oracle over all 31 strings of length <= 4.
        from functools import lru_cache
        @lru_cache(None)
        def oracle(a, b):
            if not a: return len(b)
            if not b: return len(a)
            return min(oracle(a[1:], b[1:]) + (a[0] != b[0]), oracle(a[1:], b) + 1, oracle(a, b[1:]) + 1)
        strings = ["".join(x) for n in range(5) for x in itertools.product("ab", repeat=n)]
        for a in strings:
            for b in strings:
                row = ev.edit_counts(a, b)
                self.assertEqual(row["E"], oracle(a, b))
                self.assertEqual(len(a) - row["D"] + row["I"], len(b))
                self.assertEqual(row["E"], row["S"] + row["D"] + row["I"])


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gold = [self.row("synth_1", "a", "synthetic_group_1"), self.row("synth_2", "bbbbbbbbb", "synthetic_group_2")]
        self.pred = [{"utterance_id": u, "system": s, "text": t} for s, pairs in
                     [("base", [("synth_1", "x"), ("synth_2", "bbbbbbbbb")]),
                      ("candidate", [("synth_1", "a"), ("synth_2", "bbbbbbbbx")])]
                     for u, t in pairs]
        self.config = {"schema_version": ev.SCHEMA, "split": "dev", "systems": ["base", "candidate"], "baseline": "base",
                       "oracle_candidates": ["candidate", "base"], "secondary_filter": "off", "bootstrap": {"iterations": 0, "seed": 17}}
        self.meta = {"schema_version": "cantoai-gold-metadata-v1", "annotation_version": "synthetic-v1",
                     "reference_origin": "synthetic_fixture_not_human", "origin_declaration": "Generated synthetic fixture; no human annotation.", "gold_sha256": ""}
        self.reservation = {"schema_version": "cantoai-dev-reservation-v1", "utterance_ids": ["reserved_dev_1"],
                            "source_groups": ["reserved_dev_group"], "declaration": "Synthetic development reservation fixture only."}
        self.exclusions = None
        self.test_mode = False

    def row(self, uid, reference, group):
        return {"utterance_id": uid, "source_group": group, "reference": reference, "reference_status": "synthetic_fixture",
                "split": "dev", "annotation_version": "synthetic-v1"}

    def write_json(self, name, obj):
        p = self.root / name
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return p

    def save(self):
        for name, rows in [("gold.jsonl", self.gold), ("predictions.jsonl", self.pred)]:
            (self.root / name).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
        self.meta["gold_sha256"] = ev.sha((self.root / "gold.jsonl").read_bytes())
        self.write_json("metadata.json", self.meta)
        self.write_json("config.json", self.config)
        self.write_json("reservation.json", self.reservation)
        if self.exclusions is not None:
            self.write_json("exclusions.json", self.exclusions)

    def run_eval(self, save=True, **kwargs):
        if save: self.save()
        return ev.evaluate(self.root / "gold.jsonl", self.root / "predictions.jsonl", self.root / "metadata.json",
                           self.root / "config.json", self.root / "output",
                           exclusions_path=self.root / "exclusions.json" if self.exclusions is not None else None,
                           reservation_path=self.root / "reservation.json" if self.test_mode else None,
                           freeze_path=self.root / "freeze.json" if self.test_mode else None,
                           synthetic=kwargs.get("synthetic", True))

    def freeze(self):
        self.test_mode = True
        self.config["split"] = "test"
        for row in self.gold: row["split"] = "test"
        self.save()
        ev.create_freeze(self.root / "config.json", self.root / "reservation.json", self.root / "freeze.json", True)

    def assert_rejected(self, phrase, **kwargs):
        with self.assertRaisesRegex(ev.EvaluationError, phrase):
            self.run_eval(**kwargs)
        self.assertFalse((self.root / "output").exists())

    def test_weighted_denominator_not_mean(self):
        r = self.run_eval()
        self.assertEqual(r["metrics"]["raw"]["systems"]["base"]["CER"], .1)  # mean utterance CER would be .5
        self.assertEqual(r["run_kind"], "SYNTHETIC FIXTURE ONLY - NO EMPIRICAL RESULT")

    def test_paired_error_accounting_and_text_coverage(self):
        d = self.run_eval()["metrics"]["raw"]["paired_to_baseline"]["candidate"]
        self.assertEqual((d["improved_utterances"], d["worsened_utterances"], d["equal_error_utterances"]), (1, 1, 0))
        self.assertEqual((d["fixed_errors_by_utterance_total"], d["introduced_errors_by_utterance_total"], d["net_fixed_minus_introduced"]), (1, 1, 0))
        self.assertEqual(d["changed_text_coverage"]["normalized_text_changed"], 2)

    def test_delta_sign_improvement_negative(self):
        self.pred[-1]["text"] = "bbbbbbbbb"
        d = self.run_eval()["metrics"]["raw"]["paired_to_baseline"]["candidate"]
        self.assertEqual(d["delta_E_system_minus_baseline"], -1)
        self.assertEqual(d["delta_CER_system_minus_baseline"], -.1)
        self.assertEqual(d["delta_CER_percentage_points"], -10)
        self.assertEqual(d["net_fixed_minus_introduced"], 1)

    def test_delta_sign_regression_positive(self):
        self.pred[2]["text"] = "xxx"
        d = self.run_eval()["metrics"]["raw"]["paired_to_baseline"]["candidate"]
        self.assertGreater(d["delta_CER_system_minus_baseline"], 0)
        self.assertLess(d["net_fixed_minus_introduced"], 0)

    def test_empty_reference_insertions_count(self):
        self.gold[0]["reference"] = ""
        self.pred[0]["text"] = "xx"
        r = self.run_eval()["metrics"]["raw"]["systems"]["base"]
        self.assertEqual((r["N"], r["I"], r["CER"]), (9, 2, 2/9))

    def test_explicit_empty_hypothesis_valid(self):
        self.pred[0]["text"] = ""
        self.assertEqual(self.run_eval()["metrics"]["raw"]["systems"]["base"]["D"], 1)

    def test_all_empty_reference_error(self):
        for row in self.gold: row["reference"] = ""
        self.assert_rejected("denominator N=0")

    def test_secondary_zero_denominator_error(self):
        self.config["secondary_filter"] = "unicode-punctuation-whitespace-v1"
        for row in self.gold: row["reference"] = "， \n"
        self.assert_rejected("denominator N=0 for secondary")

    def test_missing_uid_not_empty(self):
        self.pred.pop()
        self.assert_rejected("UID coverage mismatch")

    def test_extra_uid_rejected(self):
        self.pred.append({"utterance_id": "extra", "system": "base", "text": ""})
        self.assert_rejected("UID coverage mismatch")

    def test_missing_system_rejected(self):
        self.pred = self.pred[:2]
        self.assert_rejected("UID coverage mismatch")

    def test_unknown_system_rejected(self):
        self.pred[0]["system"] = "unknown"
        self.assert_rejected("unexpected system")

    def test_duplicate_gold(self):
        self.gold.append(dict(self.gold[0]))
        self.assert_rejected("duplicate gold")

    def test_duplicate_prediction_pair(self):
        self.pred.append(dict(self.pred[0]))
        self.assert_rejected("duplicate prediction")

    def test_pending_rejected_even_with_exclusion(self):
        self.gold[0]["reference_status"] = "pending"
        self.exclusions = {"schema_version": "cantoai-exclusions-v1", "excluded": [{"utterance_id": "synth_1", "reason": "still pending"}]}
        self.assert_rejected("pending reference rejected")

    def test_uncertainty_marker_rejected(self):
        self.gold[0]["reference"] = "我[听不清]"
        self.assert_rejected("uncertainty marker")

    def test_unscorable_requires_explicit_manifest(self):
        self.gold[0]["reference_status"] = "unscorable"
        self.assert_rejected("exclusions must exactly match")

    def test_unscorable_exclusion_reports_coverage(self):
        self.gold[0]["reference_status"] = "unscorable"
        self.gold[0]["reference"] = "[听不清]"
        self.exclusions = {"schema_version": "cantoai-exclusions-v1", "excluded": [{"utterance_id": "synth_1", "reason": "Synthetic ambiguity fixture"}]}
        r = self.run_eval()
        self.assertEqual(r["coverage"]["scored_utterance_fraction"], .5)
        self.assertEqual(r["metrics"]["raw"]["systems"]["base"]["N"], 9)

    def test_excluded_still_requires_prediction(self):
        self.gold[0]["reference_status"] = "unscorable"
        self.exclusions = {"schema_version": "cantoai-exclusions-v1", "excluded": [{"utterance_id": "synth_1", "reason": "Synthetic"}]}
        self.pred.pop(0)
        self.assert_rejected("UID coverage mismatch")

    def test_synthetic_rejected_in_human_mode(self):
        self.assert_rejected("reference_origin must explicitly be human_verified", synthetic=False)

    def test_human_status_not_inferred_for_synthetic(self):
        self.gold[0]["reference_status"] = "human_verified"
        self.assert_rejected("invalid reference_status")

    def test_version_mismatch(self):
        self.gold[0]["annotation_version"] = "wrong-version"
        self.assert_rejected("annotation version mismatch")

    def test_metadata_checksum_mismatch(self):
        self.save()
        self.meta["gold_sha256"] = "0" * 64
        self.write_json("metadata.json", self.meta)
        self.assert_rejected("gold checksum mismatch", save=False)

    def test_oracle_fixed_tie_order_and_same_candidates(self):
        self.pred[-1]["text"] = "bbbbbbbbb"
        r = self.run_eval()["metrics"]["raw"]["same_candidate_oracle"]
        self.assertEqual(r["aggregate"]["E"], 0)
        self.assertEqual([x["system"] for x in r["selections"]], ["candidate", "candidate"])
        self.assertIn("NON-DEPLOYABLE", r["label"])

    def test_oracle_unknown_candidate_rejected(self):
        self.config["oracle_candidates"].append("outside")
        self.assert_rejected("oracle candidates must")

    def test_secondary_changed_text_and_english_digits(self):
        self.config["secondary_filter"] = "unicode-punctuation-whitespace-v1"
        self.gold[0]["reference"] = "A1，"
        self.pred[0]["text"] = "A1，"
        self.pred[2]["text"] = "A1 "
        r = self.run_eval()
        self.assertEqual(r["metrics"]["secondary"]["systems"]["base"]["N"], 11)
        d = r["metrics"]["secondary"]["paired_to_baseline"]["candidate"]["changed_text_coverage"]
        self.assertEqual((d["exact_text_changed"], d["normalized_text_changed"]), (2, 1))

    def test_test_requires_freeze_and_dev_reservation(self):
        self.config["split"] = "test"
        for row in self.gold: row["split"] = "test"
        self.assert_rejected("test requires --dev-reservation")

    def test_valid_freeze(self):
        self.freeze()
        self.assertEqual(self.run_eval(save=False)["coverage"]["scored_utterances"], 2)

    def test_config_changed_after_freeze(self):
        self.freeze()
        self.config["secondary_filter"] = "unicode-punctuation-whitespace-v1"
        self.write_json("config.json", self.config)
        self.assert_rejected("test config changed after freeze", save=False)

    def test_source_changed_after_freeze(self):
        self.freeze()
        frozen = json.loads((self.root / "freeze.json").read_text())
        frozen["source_sha256"] = "0" * 64
        self.write_json("freeze.json", frozen)
        self.assert_rejected("evaluator source changed", save=False)

    def test_reservation_changed_after_freeze(self):
        self.freeze()
        self.reservation["utterance_ids"].append("different")
        self.write_json("reservation.json", self.reservation)
        self.assert_rejected("dev reservation changed", save=False)

    def test_dev_test_uid_overlap(self):
        self.reservation["utterance_ids"] = ["synth_1"]
        self.freeze()
        self.assert_rejected("dev/test utterance overlap", save=False)

    def test_dev_test_source_overlap_even_disjoint_uid(self):
        self.reservation["source_groups"] = ["synthetic_group_1"]
        self.freeze()
        self.assert_rejected("dev/test source_group overlap", save=False)

    def test_mixed_split_rejected(self):
        self.gold[0]["split"] = "test"
        self.assert_rejected("gold split mismatch")

    def test_freeze_requires_declaration(self):
        self.save()
        with self.assertRaisesRegex(ev.EvaluationError, "declare-before-test"):
            ev.create_freeze(self.root / "config.json", self.root / "reservation.json", self.root / "freeze.json", False)

    def test_bootstrap_reproducible(self):
        self.config["bootstrap"]["iterations"] = 1000
        r = self.run_eval()["metrics"]["raw"]["source_group_bootstrap"]
        rows = {"base": [ev.edit_counts("a", "x"), ev.edit_counts("bbbbbbbbb", "bbbbbbbbb")],
                "candidate": [ev.edit_counts("a", "a"), ev.edit_counts("bbbbbbbbb", "bbbbbbbbx")]}
        r2 = ev.bootstrap(rows, ["synthetic_group_1", "synthetic_group_2"], "base", 1000, 17)
        self.assertEqual(r, r2)
        self.assertEqual(r["valid_iterations"], 1000)
        self.assertTrue(any("speaker independence" in w for w in r["warnings"]))
        self.assertEqual(r["systems"]["base"]["delta_CER_system_minus_baseline_95CI"], [0, 0])

    def test_bootstrap_one_group_no_ci(self):
        rows = {"base": [ev.edit_counts("a", "x")]}
        r = ev.bootstrap(rows, ["g"], "base", 1000, 17)
        self.assertEqual(r["systems"], {})
        self.assertEqual(r["valid_iterations"], 0)

    def test_bootstrap_zero_denominator_draws_counted(self):
        rows = {"base": [ev.edit_counts("", "x"), ev.edit_counts("a", "a")]}
        r = ev.bootstrap(rows, ["g0", "g1"], "base", 1000, 17)
        self.assertGreater(r["zero_denominator_iterations"], 0)
        self.assertEqual(r["valid_iterations"] + r["zero_denominator_iterations"], 1000)

    def test_inputs_unchanged_output_hashes_source_saved(self):
        self.save()
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.run_eval(save=False)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()})
        manifest = json.loads((self.root / "output" / "manifest.json").read_text())
        self.assertEqual(manifest["source_sha256"], ev.source_sha())
        for name, meta in manifest["output_files"].items():
            self.assertEqual(meta["sha256"], ev.sha((self.root / "output" / name).read_bytes()))

    def test_output_overwrite_refused(self):
        self.run_eval()
        with self.assertRaisesRegex(ev.EvaluationError, "output directory already exists"):
            self.run_eval()

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ev.EvaluationError, "duplicate JSON key"):
            ev.decode('{"system":"a","system":"b"}', "synthetic")

    def test_invalid_numbers_rejected(self):
        with self.assertRaisesRegex(ev.EvaluationError, "invalid number"):
            ev.decode('{"x": NaN}', "synthetic")

    def test_unknown_config_key_rejected(self):
        self.config["casefold"] = True
        self.assert_rejected("unknown fields")

    def test_jsonl_unicode_separator_inside_string(self):
        self.gold[0]["reference"] = "a\u2028b"
        self.pred[0]["text"] = "a\u2028b"
        self.assertEqual(self.run_eval()["metrics"]["raw"]["systems"]["base"]["N"], 12)

    def test_optional_dev_reservation_enforced(self):
        self.save()
        with self.assertRaisesRegex(ev.EvaluationError, "dev utterance absent from reservation"):
            ev.evaluate(self.root / "gold.jsonl", self.root / "predictions.jsonl", self.root / "metadata.json",
                        self.root / "config.json", self.root / "output", reservation_path=self.root / "reservation.json", synthetic=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
