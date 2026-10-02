"""Generated synthetic fixtures only; never loads published rows, audio or models."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adapter as a

from synthetic_fixture import build_fixture


def configuration(split='dev'):
    return {'schema_version': 'cantoai-external-run-config-v1', 'split': split,
        'systems': ['SYNTHETIC_ONLY'], 'baseline': 'SYNTHETIC_ONLY',
        'bootstrap': {'iterations': 0, 'seed': 17},
        'model_specs': {'SYNTHETIC_ONLY': {'model_id': a.SYNTHETIC, 'model_revision': 'synthetic-v1',
            'weights_sha256': a.sha(b'NO MODEL WEIGHTS'), 'decoder_configuration': {'kind': 'synthetic'},
            'prompt_sha256': a.sha(b'NO PROMPT'), 'runtime_version': 'synthetic fixture'}}}


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.bundle, self.pins, _, _ = build_fixture(Path(self.temp.name))
        self.rows, self.audio, self.policy, self.meta, self.bundle_sha = a.load_bundle(self.bundle, source_pins_path=self.pins)

    def reject(self, phrase):
        with self.assertRaisesRegex(a.Error, phrase):
            a.validate_sources(self.rows, self.audio)

    def test_frozen_bundle_valid(self):
        self.assertEqual(len(self.rows), 30)
        self.assertEqual(sum(r['evaluation_role'] == 'dev_smoke' for r in self.rows), 10)
        self.assertTrue(all(r['speaker_id'] is None for r in self.rows))

    def test_split_disjointness(self):
        self.rows[-1]['source_text_id'] = self.rows[0]['source_text_id']
        self.reject('duplicate source IDs')

    def test_duplicate_source_id_within_dev(self):
        self.rows[1]['source_text_id'] = self.rows[0]['source_text_id']
        self.reject('duplicate source IDs')

    def test_duplicate_sample_id(self):
        self.rows[1] = copy.deepcopy(self.rows[0])
        self.reject('duplicate reference sample_id')

    def test_dropped_reference(self):
        self.rows.pop(); self.reject('reference coverage')

    def test_dropped_audio_receipt(self):
        self.audio.pop(); self.reject('audio receipt coverage')

    def test_duplicate_audio_receipt(self):
        self.audio[1] = copy.deepcopy(self.audio[0]); self.reject('coverage or duplicate')

    def test_source_revision_mismatch(self):
        self.rows[0]['dataset_revision'] = 'another-revision'; self.reject('provenance mismatch')

    def test_license_mismatch(self):
        self.rows[0]['license'] = 'unknown'; self.reject('provenance mismatch')

    def test_not_internal_manual_gold(self):
        self.rows[0]['reference_origin'] = 'human_verified'; self.reject('reference origin mismatch')

    def test_audio_reference_provenance(self):
        self.audio[0]['raw_transcription_sha256'] = '0' * 64; self.reject('audio provenance mismatch')

    def test_no_unverified_decode(self):
        self.audio[0]['decode_verified'] = False; self.reject('receipt must attest')

    def test_no_false_overlap_claim(self):
        self.rows[0]['model_pretraining_overlap'] = 'none'; self.reject('overlap status')

    def test_no_local_mapping(self):
        self.rows[0]['local_text_transformations'] = ['系->係']; self.reject('transformations / mappings')

    def test_raw_and_normalized_choice_preserved(self):
        for field in ('transcription', 'raw_transcription'):
            actual = a.convert(self.rows, field, 'dev')
            expected = [r[field] for r in self.rows if r['evaluation_role'] == 'dev_smoke']
            self.assertEqual([r['reference'] for r in actual], expected)
            self.assertEqual({r['reference_status'] for r in actual}, {a.ORIGIN})
        self.assertNotEqual(a.convert(self.rows, 'transcription', 'dev'), a.convert(self.rows, 'raw_transcription', 'dev'))

    def test_invalid_reference_choice(self):
        with self.assertRaises(a.Error): a.policy('best_of_both', 'off')

    def test_invalid_normalization(self):
        with self.assertRaises(a.Error): a.policy('transcription', 'drop_english')

    def test_split_role_mismatch(self):
        self.rows[0]['source_split'] = 'test'; self.reject('split / evaluation role mismatch')

    def test_raw_reference_mutation(self):
        self.rows[0]['raw_transcription'] += '!'; self.reject('checksum mismatch')

    def test_path_traversal(self):
        self.audio[0]['relative_audio_path'] = '../secret.wav'; self.reject('invalid audio path')

    def test_source_group_not_split_scoped(self):
        other = dict(self.rows[0], source_split='test', evaluation_role='heldout_smoke')
        self.assertEqual(a.source_group(other), a.source_group(self.rows[0]))

    def test_original_harness_stays_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            gold = a.convert(self.rows, 'transcription', 'dev')
            (d/'gold').write_bytes(a.lbytes(gold))
            (d/'pred').write_bytes(a.lbytes([{'utterance_id': g['utterance_id'], 'system': 'synthetic', 'text': ''} for g in gold]))
            metadata = {'schema_version': 'cantoai-gold-metadata-v1',
                'annotation_version': gold[0]['annotation_version'], 'reference_origin': a.ORIGIN,
                'origin_declaration': 'Published FLEURS reference, not manual gold.', 'gold_sha256': a.sha((d/'gold').read_bytes())}
            (d/'meta').write_bytes(a.jbytes(metadata))
            (d/'config').write_bytes(a.jbytes({'schema_version': a.ev.SCHEMA, 'split': 'dev', 'systems': ['synthetic'],
                'baseline': 'synthetic', 'oracle_candidates': [], 'secondary_filter': 'off', 'bootstrap': {'iterations': 0, 'seed': 17}}))
            for synthetic in (False, True):
                with self.assertRaisesRegex(a.Error, 'reference_origin must explicitly'):
                    a.ev.evaluate(d/'gold', d/'pred', d/'meta', d/'config', d/'out', synthetic=synthetic)
                self.assertFalse((d/'out').exists())


class PredictionTests(unittest.TestCase):
    def setUp(self):
        self.config = configuration()
        self.pred = [{'utterance_id': u, 'system': 'SYNTHETIC_ONLY', 'text': t} for u, t in [('synth1', ''), ('synth2', '甲')]]
        self.meta = {'schema_version': 'cantoai-external-predictions-v1', 'prediction_kind': a.SYNTHETIC,
            'bundle_lock_sha256': 'synthetic_bundle', 'split': 'dev', 'config_sha256': a.sha(a.canonical(self.config)),
            'predictions_sha256': 'synthetic_sha', 'model_specs': self.config['model_specs']}

    def call(self):
        return a.validate_predictions(self.pred, self.meta, self.config, ['synth1', 'synth2'], 'synthetic_bundle', 'synthetic_sha')

    def test_exact_coverage_with_explicit_empty(self):
        self.assertEqual(self.call()['SYNTHETIC_ONLY']['synth1'], '')

    def test_missing_prediction(self):
        self.pred.pop()
        with self.assertRaisesRegex(a.Error, 'coverage mismatch'): self.call()

    def test_extra_prediction(self):
        self.pred.append({'utterance_id': 'extra', 'system': 'SYNTHETIC_ONLY', 'text': ''})
        with self.assertRaisesRegex(a.Error, 'coverage mismatch'): self.call()

    def test_duplicate_prediction(self):
        self.pred.append(dict(self.pred[0]))
        with self.assertRaisesRegex(a.Error, 'duplicate prediction'): self.call()

    def test_unknown_system(self):
        self.pred[0]['system'] = 'not_configured'
        with self.assertRaisesRegex(a.Error, 'unexpected system'): self.call()

    def test_provenance_mismatch(self):
        self.meta['bundle_lock_sha256'] = 'other'
        with self.assertRaisesRegex(a.Error, 'provenance mismatch'): self.call()

    def test_model_provenance_mismatch(self):
        self.meta['model_specs'] = {}
        with self.assertRaisesRegex(a.Error, 'provenance mismatch'): self.call()

    def test_no_drop_mapping_in_prediction(self):
        self.pred[0]['drop'] = True
        with self.assertRaisesRegex(a.Error, 'unknown fields'): self.call()

    def test_known_synthetic_cannot_claim_model_result(self):
        self.meta['prediction_kind'] = 'external_model_predictions'
        with self.assertRaisesRegex(a.Error, 'known synthetic configuration'):
            self.call()

    def test_no_unknown_prediction_kind(self):
        self.meta['prediction_kind'] = 'human_approved'
        with self.assertRaisesRegex(a.Error, 'explicit prediction provenance'): self.call()


class MechanicalTests(unittest.TestCase):
    def test_synthetic_counts_and_labels(self):
        gold = [{'utterance_id': 'synth1', 'source_group': 'synthetic_group_1', 'reference': '甲乙'},
                {'utterance_id': 'synth2', 'source_group': 'synthetic_group_2', 'reference': '丙丁戊己庚辛壬癸'}]
        pred = {'SYNTHETIC_ONLY': {'synth1': '甲丙', 'synth2': '丙丁戊己庚辛壬癸'}}
        result, per = a.score_rows(gold, pred, configuration(), a.policy('transcription', 'off'))
        self.assertEqual(result['primary']['systems']['SYNTHETIC_ONLY'], {'N': 10, 'S': 1, 'D': 0, 'I': 0, 'E': 1, 'CER': .1})
        self.assertEqual(len(per), 2)

    def test_secondary_is_separate(self):
        gold = [{'utterance_id': 'synth1', 'source_group': 'synthetic_group_1', 'reference': '甲， 乙'}]
        pred = {'SYNTHETIC_ONLY': {'synth1': '甲乙'}}
        result, _ = a.score_rows(gold, pred, configuration(), a.policy('raw_transcription', 'unicode-punctuation-whitespace-v1'))
        self.assertEqual(result['primary']['systems']['SYNTHETIC_ONLY']['D'], 2)
        self.assertEqual(result['secondary']['systems']['SYNTHETIC_ONLY']['E'], 0)
        self.assertEqual(result['primary']['reference_field'], 'raw_transcription')

    def test_no_language_mapping(self):
        self.assertEqual(a.ev.normalize('系係ABab123'), '系係ABab123')


class FreezeAndIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle, self.pins, _, _ = build_fixture(self.root)
        self.config = configuration('test')
        self.cp = self.root/'config.json'; self.cp.write_bytes(a.jbytes(self.config))
        self.fp = self.root/'freeze.json'

    def test_explicit_freeze_declaration_required(self):
        with self.assertRaisesRegex(a.Error, 'explicit operator declaration'):
            a.freeze(self.bundle, self.cp, self.fp, source_pins_path=self.pins)
        self.assertFalse(self.fp.exists())

    def test_freeze_binds_model_policy_engine_and_bundle(self):
        f = a.freeze(self.bundle, self.cp, self.fp, True, source_pins_path=self.pins)
        self.assertEqual(f['config'], self.config)
        self.assertEqual(f['engine_hashes'], a.engine_hashes())
        self.assertFalse(f['timing_independently_verified'])

    def test_no_freeze_overwrite(self):
        a.freeze(self.bundle, self.cp, self.fp, True, source_pins_path=self.pins)
        with self.assertRaises(FileExistsError): a.freeze(self.bundle, self.cp, self.fp, True, source_pins_path=self.pins)

    def test_no_output_overwrite(self):
        with self.assertRaisesRegex(a.Error, 'overwrite forbidden'):
            a.run(self.bundle, self.cp, self.root/'missing', self.root/'missing', self.root, source_pins_path=self.pins)

    def test_no_prepare_overwrite(self):
        with self.assertRaisesRegex(a.Error, 'overwrite forbidden'):
            a.prepare('missing', 'missing', self.root, 'transcription', source_pins_path=self.pins)

    def test_test_requires_freeze_before_prediction_read(self):
        with self.assertRaisesRegex(a.Error, 'test requires pre-prediction freeze'):
            a.run(self.bundle, self.cp, self.root/'missing', self.root/'missing', self.root/'out', source_pins_path=self.pins)

    def test_model_change_after_freeze(self):
        a.freeze(self.bundle, self.cp, self.fp, True, source_pins_path=self.pins)
        self.config['model_specs']['SYNTHETIC_ONLY']['model_revision'] = 'changed'
        self.cp.write_bytes(a.jbytes(self.config))
        with self.assertRaisesRegex(a.Error, 'frozen config/model/policy/source changed'):
            a.run(self.bundle, self.cp, self.root/'missing', self.root/'missing', self.root/'out', self.fp, source_pins_path=self.pins)

    def test_engine_change_after_freeze(self):
        a.freeze(self.bundle, self.cp, self.fp, True, source_pins_path=self.pins)
        with patch.object(a, 'engine_hashes', return_value={'adapter.py': 'changed'}):
            with self.assertRaisesRegex(a.Error, 'frozen config/model/policy/source changed'):
                a.run(self.bundle, self.cp, self.root/'missing', self.root/'missing', self.root/'out', self.fp, source_pins_path=self.pins)

    def test_unknown_config_mapping_rejected(self):
        self.config['drop_english'] = True
        with self.assertRaisesRegex(a.Error, 'unknown fields'): a.validate_config(self.config)

    def test_full_run_synthetic_toy_only(self):
        # The production loader is mocked ONLY inside this test to supply two
        # wholly fabricated records. No public heldout/reference CER is computed.
        c = configuration('dev'); self.cp.write_bytes(a.jbytes(c))
        source = [{'sample_id': 'synth1', 'source_text_id': 1, 'evaluation_role': 'dev_smoke', 'transcription': '甲乙', 'duration_seconds': 1},
                  {'sample_id': 'synth2', 'source_text_id': 2, 'evaluation_role': 'dev_smoke', 'transcription': '丙丁', 'duration_seconds': 1}]
        pp = self.root/'pred.jsonl'; pp.write_bytes(a.lbytes([{'utterance_id': 'synth1', 'system': 'SYNTHETIC_ONLY', 'text': '甲'},
                                                            {'utterance_id': 'synth2', 'system': 'SYNTHETIC_ONLY', 'text': '丙丁'}]))
        mp = self.root/'meta.json'; mp.write_bytes(a.jbytes({'schema_version': 'cantoai-external-predictions-v1',
            'prediction_kind': a.SYNTHETIC, 'bundle_lock_sha256': 'synthetic_bundle', 'split': 'dev',
            'config_sha256': a.sha(a.canonical(c)), 'predictions_sha256': a.sha(pp.read_bytes()), 'model_specs': c['model_specs']}))
        loader = (source, [], a.policy('transcription', 'off'), {'limitations': ['SYNTHETIC ONLY'], 'overlap': {}}, 'synthetic_bundle')
        with patch.object(a, 'load_bundle', return_value=loader):
            result = a.run(self.bundle, self.cp, pp, mp, self.root/'out', source_pins_path=self.pins)
        self.assertEqual(result['run_kind'], a.SYNTHETIC)
        self.assertFalse(result['is_model_result'])
        self.assertEqual(result['metrics']['primary']['systems']['SYNTHETIC_ONLY']['D'], 1)
        self.assertTrue((self.root/'out/run_manifest.json').exists())

    def test_config_freeze_hashes_captured_bytes(self):
        original = self.cp.read_bytes()
        validate = a.validate_config
        def mutate_after_parse(config):
            self.cp.write_bytes(b'{"changed_after_read":true}')
            return validate(config)
        with patch.object(a, 'validate_config', side_effect=mutate_after_parse):
            frozen = a.freeze(self.bundle, self.cp, self.fp, True, source_pins_path=self.pins)
        self.assertEqual(frozen['config_file_sha256'], a.sha(original))
        self.assertEqual(frozen['config'], self.config)

    def test_bundle_snapshot_survives_post_validation_file_change(self):
        import shutil
        bundle = self.root/'bundle'; shutil.copytree(self.bundle, bundle)
        original = (bundle/'source_records.jsonl').read_bytes()
        parse = a.parse_jsonl
        changed = False
        def mutate_after_capture(data, label):
            nonlocal changed
            if label == 'source_records.jsonl' and not changed:
                changed = True
                (bundle/'source_records.jsonl').write_bytes(b'{"corrupted":true}\n')
            return parse(data, label)
        with patch.object(a, 'parse_jsonl', side_effect=mutate_after_capture):
            loaded = a.load_bundle(bundle, source_pins_path=self.pins)
        self.assertTrue(changed)
        self.assertEqual(a.lbytes(loaded[0]), original)
        with self.assertRaisesRegex(a.Error, 'checksum mismatch'):
            a.load_bundle(bundle, source_pins_path=self.pins)

    def test_prediction_config_metadata_single_snapshot(self):
        c = configuration('dev'); self.cp.write_bytes(a.jbytes(c))
        source = [{'sample_id': 'synth1', 'source_text_id': 1, 'evaluation_role': 'dev_smoke', 'transcription': '甲乙', 'duration_seconds': 1}]
        pp = self.root/'pred.jsonl'
        pp.write_bytes(a.lbytes([{'utterance_id': 'synth1', 'system': 'SYNTHETIC_ONLY', 'text': '丙丁'}]))
        original_predictions = pp.read_bytes()
        mp = self.root/'meta.json'
        mp.write_bytes(a.jbytes({'schema_version': 'cantoai-external-predictions-v1',
            'prediction_kind': a.SYNTHETIC, 'bundle_lock_sha256': 'synthetic_bundle', 'split': 'dev',
            'config_sha256': a.sha(a.canonical(c)), 'predictions_sha256': a.sha(original_predictions), 'model_specs': c['model_specs']}))
        original_config, original_metadata = self.cp.read_bytes(), mp.read_bytes()
        loader = (source, [], a.policy('transcription', 'off'), {'limitations': ['SYNTHETIC ONLY'], 'overlap': {}}, 'synthetic_bundle')
        parse = a.parse_jsonl
        def mutate_after_capture(data, label):
            if Path(label) == pp:
                pp.write_bytes(a.lbytes([{'utterance_id': 'synth1', 'system': 'SYNTHETIC_ONLY', 'text': '甲乙'}]))
                self.cp.write_bytes(b'{"changed":true}')
                mp.write_bytes(b'{"changed":true}')
            return parse(data, label)
        with patch.object(a, 'load_bundle', return_value=loader), patch.object(a, 'parse_jsonl', side_effect=mutate_after_capture):
            result = a.run(self.bundle, self.cp, pp, mp, self.root/'out', source_pins_path=self.pins)
        self.assertEqual(result['metrics']['primary']['systems']['SYNTHETIC_ONLY']['S'], 2)
        self.assertEqual((self.root/'out/config.json').read_bytes(), original_config)
        self.assertEqual((self.root/'out/prediction_metadata.json').read_bytes(), original_metadata)
        self.assertEqual(a.jread(self.root/'out/run_manifest.json')['predictions_sha256'], a.sha(original_predictions))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(a.Error, 'duplicate JSON key'):
            a.ev.decode('{"x":1,"x":2}', 'synthetic')

if __name__ == '__main__': unittest.main(verbosity=2)
