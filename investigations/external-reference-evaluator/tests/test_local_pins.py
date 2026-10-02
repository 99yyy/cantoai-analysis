"""Offline end-to-end checks of the explicit local trust boundary."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adapter as a
from synthetic_fixture import build_fixture
from test_adapter import configuration


class LocalPinsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle, self.pins, self.reference, self.audio = build_fixture(self.root)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(a.ROOT/'adapter.py'), *map(str, args)],
                              capture_output=True, text=True, check=False)

    def refresh_status(self):
        files = {p.name: a.sha(p.read_bytes()) for p in self.bundle.iterdir() if p.name != 'STATUS.json'}
        (self.bundle/'STATUS.json').write_bytes(a.jbytes({'status': 'complete', 'files': files}))

    def test_incomplete_bundle_rejected(self):
        (self.bundle/'STATUS.json').write_bytes(a.jbytes({'status': 'running'}))
        with self.assertRaisesRegex(a.Error, 'bundle output is not complete'):
            a.load_bundle(self.bundle, self.pins)

    def test_non_object_status_rejected(self):
        (self.bundle/'STATUS.json').write_bytes(a.jbytes([]))
        with self.assertRaisesRegex(a.Error, 'bundle output is not complete'):
            a.load_bundle(self.bundle, self.pins)

    def test_status_mismatch_rejected(self):
        status = a.jread(self.bundle/'STATUS.json')
        status['files']['bundle_lock.json'] = '0' * 64
        (self.bundle/'STATUS.json').write_bytes(a.jbytes(status))
        with self.assertRaisesRegex(a.Error, 'bundle status checksum mismatch'):
            a.load_bundle(self.bundle, self.pins)

    def test_completed_output_has_hashes_and_no_temporary_files(self):
        status = a.jread(self.bundle/'STATUS.json')
        self.assertEqual(status['status'], 'complete')
        self.assertFalse(list(self.bundle.glob('.partial-*')))
        for name, digest in status['files'].items():
            self.assertEqual(a.sha((self.bundle/name).read_bytes()), digest)

    def test_missing_pins_fail_closed(self):
        with self.assertRaisesRegex(a.Error, 'explicit trusted source pins required'):
            a.load_bundle(self.bundle)
        result = self.cli('validate', '--bundle', self.bundle)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--source-pins', result.stderr)

    def test_pins_reject_path_traversal(self):
        pins = a.jread(self.pins)
        pins['reference']['../outside'] = '0' * 64
        self.pins.write_bytes(a.jbytes(pins))
        with self.assertRaisesRegex(a.Error, 'trusted source pin file names mismatch'):
            a.pinned_source(self.pins)

    def test_pins_reject_invalid_digest(self):
        pins = a.jread(self.pins)
        pins['projection']['source_records_sha256'] = 'not-a-hash'
        self.pins.write_bytes(a.jbytes(pins))
        with self.assertRaisesRegex(a.Error, 'must be lowercase SHA-256'):
            a.pinned_source(self.pins)

    def test_source_mutation_rejected_before_prepare(self):
        (self.reference/'reference_30.jsonl').write_text('{}\n')
        with self.assertRaisesRegex(a.Error, 'frozen source hash mismatch'):
            a.prepare(self.reference, self.audio, self.root/'out', 'transcription', source_pins_path=self.pins)
        self.assertFalse((self.root/'out').exists())

    def test_bundle_cannot_choose_its_own_pins(self):
        pins = a.jread(self.bundle/'source_pins.json')
        pins['projection']['source_records_sha256'] = '0' * 64
        (self.bundle/'source_pins.json').write_bytes(a.jbytes(pins))
        lock = a.jread(self.bundle/'bundle_lock.json')
        lock['files']['source_pins.json'] = a.sha((self.bundle/'source_pins.json').read_bytes())
        (self.bundle/'bundle_lock.json').write_bytes(a.jbytes(lock))
        self.refresh_status()
        with self.assertRaisesRegex(a.Error, 'source pins changed'):
            a.load_bundle(self.bundle, self.pins)

    def test_prepare_rejects_inconsistent_projection_pins(self):
        pins = a.jread(self.pins)
        pins['projection']['source_records_sha256'] = '0' * 64
        self.pins.write_bytes(a.jbytes(pins))
        with self.assertRaisesRegex(a.Error, 'source projection differs from trusted pins'):
            a.prepare(self.reference, self.audio, self.root/'bad-bundle', 'transcription', source_pins_path=self.pins)
        self.assertFalse((self.root/'bad-bundle').exists())

    def test_rehashed_metadata_cannot_remove_limitations(self):
        meta = a.jread(self.bundle/'metadata.json')
        meta['limitations'] = ['Fabricated claim of universal model quality']
        (self.bundle/'metadata.json').write_bytes(a.jbytes(meta))
        lock = a.jread(self.bundle/'bundle_lock.json')
        lock['files']['metadata.json'] = a.sha((self.bundle/'metadata.json').read_bytes())
        (self.bundle/'bundle_lock.json').write_bytes(a.jbytes(lock))
        self.refresh_status()
        with self.assertRaisesRegex(a.Error, 'metadata provenance mismatch'):
            a.load_bundle(self.bundle, self.pins)

    def test_cli_prepare_validate_freeze_and_synthetic_run(self):
        bundle = self.root/'cli-bundle'
        result = self.cli('prepare', '--reference-dir', self.reference, '--audio-dir', self.audio,
                          '--out', bundle, '--reference-field', 'raw_transcription', '--source-pins', self.pins)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli('validate', '--bundle', bundle, '--source-pins', self.pins)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['audio_opened'])
        config = configuration('test')
        cp = self.root/'config.json'; cp.write_bytes(a.jbytes(config))
        fp = self.root/'freeze.json'
        result = self.cli('freeze', '--bundle', bundle, '--config', cp, '--output', fp,
                          '--declare-before-test-predictions', '--source-pins', self.pins)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows, _, policy, _, bundle_hash = a.load_bundle(bundle, self.pins)
        pp = self.root/'predictions.jsonl'
        pp.write_bytes(a.lbytes([{'utterance_id': row['utterance_id'], 'system': 'SYNTHETIC_ONLY', 'text': ''}
                                for row in a.convert(rows, policy['reference_field'], 'test')]))
        mp = self.root/'prediction-metadata.json'
        mp.write_bytes(a.jbytes({'schema_version': 'cantoai-external-predictions-v1',
            'prediction_kind': a.SYNTHETIC, 'bundle_lock_sha256': bundle_hash, 'split': 'test',
            'config_sha256': a.sha(a.canonical(config)), 'predictions_sha256': a.sha(pp.read_bytes()),
            'model_specs': config['model_specs']}))
        result = self.cli('run', '--bundle', bundle, '--config', cp, '--predictions', pp,
                          '--prediction-metadata', mp, '--out', self.root/'result', '--freeze', fp,
                          '--source-pins', self.pins)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = a.jread(self.root/'result/report.json')
        self.assertEqual(report['run_kind'], a.SYNTHETIC)
        self.assertFalse(report['is_model_result'])
        self.assertFalse(report['freeze_timing_independently_verified'])


if __name__ == '__main__': unittest.main(verbosity=2)
