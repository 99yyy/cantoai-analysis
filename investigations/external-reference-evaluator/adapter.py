#!/usr/bin/env python3
"""FLEURS external-reference adapter with explicit local trust pins. Standard library; no audio/model/network IO."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import types
import json
import math
from pathlib import Path, PurePosixPath
import sys
import tempfile
import os

ROOT = Path(__file__).resolve().parent
VERSION = '1.1.0'
ORIGIN = 'external_published_reference'
SYNTHETIC = 'SYNTHETIC_PREDICTIONS_NOT_MODEL_RESULT'
REVISION = '70bb2e84b976b7e960aa89f1c648e09c59f894dd'
VENDOR_SHA = 'f7e19e9a3686a8d7db7099c385134ebc92226e8e775a23177874c2fb786aee14'
OVERLAP = ('existing_cantoai_byte_overlap', 'existing_cantoai_content_overlap',
           'existing_cantoai_speaker_overlap', 'model_pretraining_overlap')
ROLES = {'dev_smoke': ('validation', 'dev', 10), 'heldout_smoke': ('test', 'test', 20)}
SOURCE_FIELDS = ('sample_id', 'dataset', 'config', 'dataset_revision', 'license',
    'evaluation_role', 'source_split', 'source_row_index', 'source_text_id',
    'source_audio_basename', 'source_snapshot_kind', 'source_snapshot_sha256',
    'raw_transcription', 'raw_transcription_sha256', 'transcription',
    'transcription_sha256', 'reference_origin', 'local_text_transformations',
    'speaker_id', 'num_samples', 'sampling_rate_hz', 'duration_seconds') + OVERLAP
AUDIO_FIELDS = ('sample_id', 'source_split', 'source_text_id', 'source_audio_basename',
    'evaluation_role', 'license', 'relative_audio_path', 'audio_sha256', 'audio_bytes',
    'reference_file_sha256', 'transcription_sha256', 'raw_transcription_sha256',
    'decode_verified', 'decode_method', 'measurements', 'ffprobe', 'listened_to',
    'model_inference_performed') + OVERLAP

def sha(data):
    return hashlib.sha256(data).hexdigest()

# This unchanged module supplies only tested JSON/metric primitives. Its run() guard
# is never bypassed, monkeypatched, or called with relabeled published references.
_VENDOR_BYTES = (ROOT / 'vendor/evaluate.py').read_bytes()
if sha(_VENDOR_BYTES) != VENDOR_SHA:
    raise RuntimeError('vendored original harness source checksum mismatch')
ev = types.ModuleType('cantoai_original_v1')
ev.__file__ = str(ROOT / 'vendor/evaluate.py')
exec(compile(_VENDOR_BYTES, ev.__file__, 'exec'), ev.__dict__)
_SOURCE_BYTES = Path(__file__).read_bytes()
Error = ev.EvaluationError
require = ev.require
canonical = ev.canonical

def jread(path):
    return ev.read_json(path)[0]

def parse_jsonl(data, label):
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise Error('invalid UTF-8 JSONL: ' + str(label)) from exc
    rows = []
    for n, line in enumerate(text.split('\n'), 1):
        if line.strip():
            row = ev.decode(line, f'{label}:{n}')
            require(isinstance(row, dict), 'JSONL row must be an object')
            rows.append(row)
    require(rows, 'empty JSONL: ' + str(label))
    return rows

def lread(path):
    return parse_jsonl(Path(path).read_bytes(), path)

def pinned_source(source_pins_path):
    """Load trusted pins supplied independently from the bundle being checked."""
    require(source_pins_path is not None, 'explicit trusted source pins required')
    pins = jread(source_pins_path)
    ev.keys(pins, ('reference', 'audio', 'projection'))
    expected = {
        'reference': {'manifest.json', 'reference_30.jsonl', 'dev_smoke.jsonl',
                      'heldout_smoke.jsonl', 'selection.json', 'license_evidence.json', 'source_evidence.json'},
        'audio': {'audio_manifest_30.jsonl', 'manifest.json', 'qa_report.json'},
        'projection': {'source_records_sha256', 'audio_receipts_sha256'},
    }
    for section, names in expected.items():
        require(isinstance(pins[section], dict) and set(pins[section]) == names,
                'trusted source pin file names mismatch: ' + section)
        for name, digest in pins[section].items():
            digest_string(digest, section + '/' + name)
    return pins

def jbytes(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()

def lbytes(rows):
    return b''.join(canonical(row) + b'\n' for row in rows)

def now():
    return datetime.now(timezone.utc).isoformat()

def fresh_dir(path):
    path = Path(path)
    require(not path.exists(), 'output directory already exists; overwrite forbidden')
    return path

def write_files(path, files):
    path = fresh_dir(path)
    path.mkdir(parents=True, exist_ok=False)
    # Reserve the directory first: concurrent callers cannot overwrite it.
    # Failed writes deliberately remain marked running and cannot be consumed.
    (path / 'STATUS.json').write_bytes(jbytes({'status': 'running'}))
    def promote(name, data):
        with tempfile.NamedTemporaryFile(dir=path, prefix='.partial-', delete=False) as f:
            temporary = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(path / name)
    for name, data in files.items():
        promote(name, data)
    promote('STATUS.json', jbytes({'status': 'complete',
                                  'files': {name: sha(data) for name, data in files.items()}}))

def digest_string(value, label):
    require(isinstance(value, str) and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), label + ' must be lowercase SHA-256')

def source_group(row):
    # Deliberately excludes split and recording ID: equal public source IDs must
    # collide across official splits, rather than be disguised as independent.
    return f"google/fleurs:yue_hant_hk:source_text:{row['source_text_id']}"

def validate_sources(rows, audio):
    require(len(rows) == 30, 'reference coverage must be exactly 30')
    require(len(audio) == 30, 'audio receipt coverage must be exactly 30')
    ids, groups, roles = set(), set(), Counter()
    raw_by_role, norm_by_role = {}, {}
    for row in rows:
        ev.keys(row, SOURCE_FIELDS)
        uid = ev.string(row['sample_id'], 'sample_id')
        require(uid not in ids, 'duplicate reference sample_id')
        ids.add(uid)
        require(type(row['source_text_id']) is int and row['source_text_id'] >= 0, 'invalid source_text_id')
        group = source_group(row)
        require(group not in groups, 'duplicate source IDs / dev-test source-group overlap')
        groups.add(group)
        require(row['evaluation_role'] in ROLES, 'invalid evaluation role')
        role = row['evaluation_role']; split, _, _ = ROLES[role]
        require(row['source_split'] == split, 'official split / evaluation role mismatch')
        roles[role] += 1
        require(type(row['source_row_index']) is int and row['source_row_index'] >= 0, 'invalid source row')
        require(uid == f"fleurs:yue_hant_hk:{split}:{row['source_row_index']}:{row['source_audio_basename']}", 'sample identity mismatch')
        require(row['dataset'] == 'google/fleurs' and row['config'] == 'yue_hant_hk' and
                row['dataset_revision'] == REVISION and row['license'] == 'CC-BY-4.0', 'provenance mismatch')
        require(row['reference_origin'] == 'official_human_read_prompt_reference_not_new_manual_transcription', 'reference origin mismatch')
        require(row['local_text_transformations'] == [], 'local transformations / mappings forbidden')
        require(row['speaker_id'] is None, 'speaker identity must remain unavailable')
        require(all(row[k] == 'unknown' for k in OVERLAP), 'overlap status must remain unknown')
        for field in ('raw_transcription', 'transcription'):
            ev.string(row[field], field)
            require(sha(row[field].encode()) == row[field + '_sha256'], field + ' checksum mismatch')
        raw_by_role.setdefault(role, set()).add(row['raw_transcription'])
        norm_by_role.setdefault(role, set()).add(row['transcription'])
        require(type(row['num_samples']) is int and row['num_samples'] > 0 and row['sampling_rate_hz'] == 16000, 'invalid sample count/rate')
        require(isinstance(row['duration_seconds'], (float, int)) and not isinstance(row['duration_seconds'], bool)
                and math.isclose(row['duration_seconds'], row['num_samples'] / 16000, abs_tol=1e-9), 'duration mismatch')
        digest_string(row['source_snapshot_sha256'], 'source_snapshot_sha256')
    require(dict(roles) == {r: v[2] for r, v in ROLES.items()}, 'split counts must remain 10 dev / 20 heldout')
    for by_role in (raw_by_role, norm_by_role):
        require(not by_role['dev_smoke'] & by_role['heldout_smoke'], 'dev/test exact transcript overlap')
    by_id = {r['sample_id']: r for r in rows}
    seen, hashes, paths = set(), set(), set()
    for a in audio:
        ev.keys(a, AUDIO_FIELDS)
        uid = a['sample_id']
        require(uid in by_id and uid not in seen, 'audio/reference coverage or duplicate mismatch')
        seen.add(uid); r = by_id[uid]
        for k in ('source_split', 'source_text_id', 'source_audio_basename', 'evaluation_role',
                  'license', 'raw_transcription_sha256', 'transcription_sha256') + OVERLAP:
            require(a[k] == r[k], 'audio provenance mismatch: ' + k)
        require(a['decode_verified'] is True and a['listened_to'] is False and
                a['model_inference_performed'] is False, 'receipt must attest decode only, no listening/inference')
        p = PurePosixPath(a['relative_audio_path'])
        require(not p.is_absolute() and '..' not in p.parts and p.suffix == '.wav' and
                len(p.parts) == 3 and p.parts[0] == 'wav' and p.name == r['source_audio_basename'], 'invalid audio path')
        require(p.parts[1] == ('dev' if r['evaluation_role'] == 'dev_smoke' else 'test'), 'audio path split mismatch')
        require(str(p) not in paths, 'duplicate audio path'); paths.add(str(p))
        digest_string(a['audio_sha256'], 'audio_sha256')
        require(a['audio_sha256'] not in hashes, 'duplicate audio hash'); hashes.add(a['audio_sha256'])
        require(type(a['audio_bytes']) is int and a['audio_bytes'] > 0, 'invalid audio size')
        m = a['measurements']; f = a['ffprobe']
        require(m['channels'] == 1 and m['sampling_rate_hz'] == 16000 and m['bits_per_sample'] == 32 and
                m['format_code'] == 3 and m['sample_frames'] == r['num_samples'] and
                math.isclose(m['duration_seconds'], r['duration_seconds'], abs_tol=1e-9), 'decode measurements mismatch')
        require(f['codec_name'] == 'pcm_f32le' and f['channels'] == 1 and f['sample_rate'] == '16000' and
                f['duration_ts'] == r['num_samples'], 'decode probe mismatch')
    require(seen == ids, 'reference/audio coverage mismatch')

def load_original(reference_dir, audio_dir, source_pins_path=None):
    pins = pinned_source(source_pins_path)
    snapshots = {}
    for label, directory in [('reference', Path(reference_dir)), ('audio', Path(audio_dir))]:
        snapshots[label] = {name: (directory / name).read_bytes() for name in pins[label]}
        for name, expected in pins[label].items():
            require(sha(snapshots[label][name]) == expected, 'frozen source hash mismatch: ' + label + '/' + name)
    manifest = ev.decode(snapshots['reference']['manifest.json'], 'reference manifest')
    am = ev.decode(snapshots['audio']['manifest.json'], 'audio manifest')
    rows0 = parse_jsonl(snapshots['reference']['reference_30.jsonl'], 'reference rows')
    audio0 = parse_jsonl(snapshots['audio']['audio_manifest_30.jsonl'], 'audio receipts')
    rows = [{k: r[k] for k in SOURCE_FIELDS} for r in rows0]
    audio = [{k: a[k] for k in AUDIO_FIELDS} for a in audio0]
    validate_sources(rows, audio)
    require(sha(lbytes(rows)) == pins['projection']['source_records_sha256'] and
            sha(lbytes(audio)) == pins['projection']['audio_receipts_sha256'],
            'source projection differs from trusted pins')
    for role, filename in [('dev_smoke', 'dev_smoke.jsonl'), ('heldout_smoke', 'heldout_smoke.jsonl')]:
        require(parse_jsonl(snapshots['reference'][filename], filename) == [r for r in rows0 if r['evaluation_role'] == role], 'split file is not exact reference subset')
    selected = ev.decode(snapshots['reference']['selection.json'], 'selection')['selected']
    require({s['sample_id'] for s in selected} == {r['sample_id'] for r in rows} and len(selected) == 30, 'selection coverage mismatch')
    for s, r in zip(selected, rows):
        require(s['sample_id'] == r['sample_id'] and s['source_text_id'] == r['source_text_id'] and
                s['role'] == r['evaluation_role'] and s['split'] == r['source_split'], 'selection identity/order mismatch')
    ref_hash = pins['reference']['reference_30.jsonl']
    require(manifest['reference_file_sha256'] == am['reference_file_sha256'] == ref_hash, 'manifest reference hash mismatch')
    require(all(a['reference_file_sha256'] == ref_hash for a in audio), 'audio reference binding mismatch')
    require(am['audio_manifest_sha256'] == pins['audio']['audio_manifest_30.jsonl'] and
            am['all_decode_verified'] is True and am['model_inference_count'] == 0, 'audio manifest mismatch')
    return rows, audio, pins

def policy(field, secondary):
    require(field in ('transcription', 'raw_transcription'), 'reference field must be explicit official transcription or raw_transcription')
    require(secondary in ('off', 'unicode-punctuation-whitespace-v1'), 'unsupported normalization or drop mapping')
    return {'reference_field': field, 'primary': ev.RAW_POLICY,
            'secondary': ev.SECONDARY_POLICY if secondary != 'off' else None,
            'secondary_filter': secondary,
            'upstream_normalization': 'Official transcription is already normalized by publisher; not recreated locally.',
            'local_reference_preservation': 'Both official fields retained byte-for-byte as decoded UTF-8 strings.',
            'prediction_preprocessing': 'Exactly the same metric-specific NFC/line-ending and optional secondary filter as reference; no hidden FLEURS FST/tokenizer.',
            'mapping_policy': 'No spelling/script/case/digit/English mappings, regex replacements, row drops, or exclusions.'}

def convert(rows, field, split):
    return [{'utterance_id': r['sample_id'], 'source_group': source_group(r),
             'reference': r[field], 'reference_status': ORIGIN, 'split': split,
             'annotation_version': 'published_fleurs_' + REVISION}
            for r in rows if ROLES[r['evaluation_role']][1] == split]

def bundle_metadata(field):
    return {'schema_version': 'cantoai-external-published-reference-v1', 'reference_origin': ORIGIN,
        'dataset': 'google/fleurs', 'config': 'yue_hant_hk', 'revision': REVISION, 'license': 'CC-BY-4.0',
        'reference_field': field, 'split_counts': {'dev': 10, 'test': 20},
        'reference_set_frozen_before_model_inference': True,
        'annotation_claim': 'Published read-prompt references; no new listening or manual CantoAI annotation.',
        'audio_validation': 'Prior full-decode receipts validated. This adapter never opens audio and does not attest current WAV bytes.',
        'limitations': ['30 samples are feasibility only; no release gate or commercial accuracy claim.',
            'Heldout is procedural and public, not secret. Never tune on test results.',
            'Source-text ID groups are not speakers. All CantoAI/pretraining overlap remains unknown.',
            'Raw primary CER counts spaces/punctuation after minimal NFC; publisher-tokenized transcription can include spaces.',
            'Secondary CER is separate and cannot silently replace primary. Do not convert CER to accuracy.'],
        'overlap': {k: 'unknown' for k in OVERLAP}, 'original_harness_direct_run_supported': False}

def prepare(reference_dir, audio_dir, out, field, secondary='off', source_pins_path=None):
    fresh_dir(out)
    rows, audio, pins = load_original(reference_dir, audio_dir, source_pins_path)
    p = policy(field, secondary)
    files = {'source_records.jsonl': lbytes(rows), 'audio_receipts.jsonl': lbytes(audio),
             'dev.gold.jsonl': lbytes(convert(rows, field, 'dev')),
             'test.gold.jsonl': lbytes(convert(rows, field, 'test')),
             'normalization.json': jbytes(p),
             'source_pins.json': jbytes(pins),
             'ATTRIBUTION.txt': (ROOT / 'ATTRIBUTION.txt').read_bytes()}
    dev = convert(rows, field, 'dev')
    files['dev_reservation.json'] = jbytes({'schema_version': 'cantoai-dev-reservation-v1',
        'utterance_ids': [r['utterance_id'] for r in dev], 'source_groups': [r['source_group'] for r in dev],
        'declaration': 'Frozen public validation rows reserved for dev; source-text grouping is not speaker identity.'})
    meta = bundle_metadata(field)
    files['metadata.json'] = jbytes(meta)
    lock = {'schema_version': 'cantoai-external-bundle-lock-v1',
            'files': {name: sha(data) for name, data in files.items()},
            'source_revision': REVISION, 'reference_origin': ORIGIN, 'adapter_version': VERSION}
    files['bundle_lock.json'] = jbytes(lock)
    write_files(out, files)
    return lock

def load_bundle(directory, source_pins_path=None):
    directory = Path(directory)
    status = jread(directory / 'STATUS.json')
    require(isinstance(status, dict) and status.get('status') == 'complete', 'bundle output is not complete')
    lock_bytes = (directory / 'bundle_lock.json').read_bytes()
    lock = ev.decode(lock_bytes, 'bundle_lock.json')
    ev.keys(lock, ('schema_version', 'files', 'source_revision', 'reference_origin', 'adapter_version'))
    require(lock['schema_version'] == 'cantoai-external-bundle-lock-v1' and lock['reference_origin'] == ORIGIN and
            lock['source_revision'] == REVISION and lock['adapter_version'] == VERSION, 'bundle provenance mismatch')
    expected_names = {'source_records.jsonl', 'audio_receipts.jsonl', 'dev.gold.jsonl', 'test.gold.jsonl',
                      'normalization.json', 'source_pins.json', 'ATTRIBUTION.txt', 'dev_reservation.json', 'metadata.json'}
    require(set(lock['files']) == expected_names, 'bundle files missing or extra')
    snapshots = {name: (directory / name).read_bytes() for name in expected_names}
    for name, digest in lock['files'].items():
        require(sha(snapshots[name]) == digest, 'bundle file checksum mismatch: ' + name)
    require(status == {'status': 'complete', 'files': {
        **{name: sha(data) for name, data in snapshots.items()},
        'bundle_lock.json': sha(lock_bytes)}}, 'bundle status checksum mismatch')
    pins = pinned_source(source_pins_path)
    require(ev.decode(snapshots['source_pins.json'], 'source_pins.json') == pins, 'source pins changed')
    rows = parse_jsonl(snapshots['source_records.jsonl'], 'source_records.jsonl')
    audio = parse_jsonl(snapshots['audio_receipts.jsonl'], 'audio_receipts.jsonl')
    require(sha(lbytes(rows)) == pins['projection']['source_records_sha256'] and
            sha(lbytes(audio)) == pins['projection']['audio_receipts_sha256'], 'published projection differs from frozen source')
    validate_sources(rows, audio)
    p = ev.decode(snapshots['normalization.json'], 'normalization.json')
    meta = ev.decode(snapshots['metadata.json'], 'metadata.json')
    require(p == policy(p['reference_field'], p['secondary_filter']), 'normalization policy changed / unsupported mapping')
    require(meta == bundle_metadata(p['reference_field']), 'metadata provenance mismatch')
    for split in ('dev', 'test'):
        require(parse_jsonl(snapshots[split + '.gold.jsonl'], split + '.gold.jsonl') == convert(rows, p['reference_field'], split), 'gold projection changed or coverage mismatch')
    dev = convert(rows, p['reference_field'], 'dev'); reservation = ev.decode(snapshots['dev_reservation.json'], 'dev_reservation.json')
    ev.validate_reservation(reservation)
    require(reservation['utterance_ids'] == [r['utterance_id'] for r in dev] and
            reservation['source_groups'] == [r['source_group'] for r in dev], 'dev reservation mismatch')
    return rows, audio, p, meta, sha(lock_bytes)

def engine_hashes():
    for name, captured in [('adapter.py', _SOURCE_BYTES), ('vendor/evaluate.py', _VENDOR_BYTES)]:
        require((ROOT / name).read_bytes() == captured, 'engine file changed after loading: ' + name)
    return {'adapter.py': sha(_SOURCE_BYTES), 'vendor/evaluate.py': VENDOR_SHA}

def validate_config(c):
    ev.keys(c, ('schema_version', 'split', 'systems', 'baseline', 'bootstrap', 'model_specs'))
    require(c['schema_version'] == 'cantoai-external-run-config-v1', 'unsupported external configuration')
    require(c['split'] in ('dev', 'test'), 'split must be dev or test')
    ev.unique_strings(c['systems'], 'systems')
    require(c['baseline'] in c['systems'], 'baseline absent from systems')
    ev.keys(c['bootstrap'], ('iterations', 'seed'))
    require(type(c['bootstrap']['iterations']) is int and c['bootstrap']['iterations'] in (0, 1000), 'bootstrap iterations must be 0 or 1000')
    require(type(c['bootstrap']['seed']) is int, 'bootstrap seed must be integer')
    require(isinstance(c['model_specs'], dict) and set(c['model_specs']) == set(c['systems']), 'exact model spec coverage required')
    for m in c['model_specs'].values():
        ev.keys(m, ('model_id', 'model_revision', 'weights_sha256', 'decoder_configuration', 'prompt_sha256', 'runtime_version'))
        for k in ('model_id', 'model_revision', 'runtime_version'):
            ev.string(m[k], k)
        for k in ('weights_sha256', 'prompt_sha256'):
            digest_string(m[k], k)
        require(isinstance(m['decoder_configuration'], dict), 'decoder configuration must be explicit JSON object')
    return c

def freeze(bundle, config_path, output, declaration=False, source_pins_path=None):
    require(declaration is True, 'requires explicit operator declaration before test predictions/scores')
    rows, audio, p, meta, bundle_sha = load_bundle(bundle, source_pins_path)
    config_bytes = Path(config_path).read_bytes()
    config = validate_config(ev.decode(config_bytes, config_path))
    require(config['split'] == 'test', 'freeze requires test config')
    payload = {'schema_version': 'cantoai-external-test-freeze-v1', 'created_utc': now(),
        'declaration': 'Operator declares evaluator, reference choice, model weights, prompt and decoder configuration were frozen before test predictions or scores.',
        'timing_independently_verified': False, 'config': config, 'config_sha256': sha(canonical(config)),
        'config_file_sha256': sha(config_bytes), 'bundle_lock_sha256': bundle_sha,
        'engine_hashes': engine_hashes(), 'policy_sha256': sha(canonical(p)),
        'reference_origin': ORIGIN}
    with Path(output).open('xb') as f:
        f.write(jbytes(payload))
    return payload

def validate_predictions(predictions, metadata, config, ids, bundle_sha, predictions_sha):
    ev.keys(metadata, ('schema_version', 'prediction_kind', 'bundle_lock_sha256', 'split',
                       'config_sha256', 'predictions_sha256', 'model_specs'))
    require(metadata['schema_version'] == 'cantoai-external-predictions-v1', 'prediction metadata schema mismatch')
    require(metadata['prediction_kind'] in (SYNTHETIC, 'external_model_predictions'), 'explicit prediction provenance required')
    require(metadata['bundle_lock_sha256'] == bundle_sha and metadata['split'] == config['split'] and
            metadata['config_sha256'] == sha(canonical(config)) and metadata['model_specs'] == config['model_specs'] and
            metadata['predictions_sha256'] == predictions_sha, 'prediction provenance mismatch')
    if metadata['prediction_kind'] == 'external_model_predictions':
        def known_synthetic(value):
            if isinstance(value, str):
                return 'synthetic' in value.casefold()
            if isinstance(value, dict):
                return any(known_synthetic(k) or known_synthetic(v) for k, v in value.items())
            if isinstance(value, list):
                return any(known_synthetic(v) for v in value)
            return False
        require(not known_synthetic(config['systems']) and not known_synthetic(config['model_specs']),
                'known synthetic configuration cannot claim model results')
    result = {s: {} for s in config['systems']}
    for r in predictions:
        ev.keys(r, ('utterance_id', 'system', 'text'))
        require(r['system'] in result, 'unexpected system')
        uid = ev.string(r['utterance_id'], 'utterance_id')
        require(uid not in result[r['system']], 'duplicate prediction pair')
        result[r['system']][uid] = ev.string(r['text'], 'prediction text', empty=True)
    for s, values in result.items():
        require(set(values) == set(ids), 'reference/prediction coverage mismatch for ' + s + '; missing is not empty')
    return result

def score_rows(gold, predictions, config, p):
    """Pure mechanical scoring; caller owns source/prediction/freeze validation."""
    require(gold, 'empty reference set')
    result = {}; per = []
    ids = [g['utterance_id'] for g in gold]
    for metric in (['primary', 'secondary'] if p['secondary'] else ['primary']):
        secondary = metric == 'secondary'
        refs = [ev.normalize(g['reference'], secondary) for g in gold]
        require(sum(map(len, refs)) > 0, 'aggregate reference denominator N=0')
        rows = {s: [ev.edit_counts(r, ev.normalize(predictions[s][u], secondary)) for r, u in zip(refs, ids)] for s in config['systems']}
        summary = {'reference_field': p['reference_field'], 'normalization': p[metric],
                   'systems': {s: ev.total(rs) for s, rs in rows.items()}}
        summary['paired_delta_CER_system_minus_baseline'] = {
            s: summary['systems'][s]['CER'] - summary['systems'][config['baseline']]['CER'] for s in rows}
        if config['bootstrap']['iterations']:
            summary['source_text_group_bootstrap'] = ev.bootstrap(rows, [g['source_group'] for g in gold], config['baseline'], **config['bootstrap'])
        result[metric] = summary
        for s, rs in rows.items():
            per.extend({'metric': metric, 'system': s, 'utterance_id': u, **r} for u, r in zip(ids, rs))
    return result, per

def run(bundle, config_path, predictions_path, prediction_metadata_path, out, freeze_path=None, source_pins_path=None):
    fresh_dir(out)
    rows, audio, p, meta, bundle_sha = load_bundle(bundle, source_pins_path)
    config_bytes = Path(config_path).read_bytes()
    config = validate_config(ev.decode(config_bytes, config_path))
    freeze_bytes = None
    if config['split'] == 'test':
        require(freeze_path is not None, 'test requires pre-prediction freeze')
        freeze_bytes = Path(freeze_path).read_bytes()
        f = ev.decode(freeze_bytes, freeze_path)
        require(f.get('schema_version') == 'cantoai-external-test-freeze-v1' and
                f.get('reference_origin') == ORIGIN and f.get('timing_independently_verified') is False and
                f.get('declaration') == 'Operator declares evaluator, reference choice, model weights, prompt and decoder configuration were frozen before test predictions or scores.', 'invalid freeze declaration')
        require(f.get('config') == config and f.get('config_sha256') == sha(canonical(config)) and
                f.get('config_file_sha256') == sha(config_bytes) and
                f.get('bundle_lock_sha256') == bundle_sha and f.get('engine_hashes') == engine_hashes() and
                f.get('policy_sha256') == sha(canonical(p)), 'frozen config/model/policy/source changed')
    else:
        require(freeze_path is None, 'test freeze not permitted for dev run')
    gold = convert(rows, p['reference_field'], config['split'])
    pb = Path(predictions_path).read_bytes()
    pm_bytes = Path(prediction_metadata_path).read_bytes()
    pm = ev.decode(pm_bytes, prediction_metadata_path)
    pred = validate_predictions(parse_jsonl(pb, predictions_path), pm, config, [g['utterance_id'] for g in gold], bundle_sha, sha(pb))
    metrics, per = score_rows(gold, pred, config, p)
    synthetic = pm['prediction_kind'] == SYNTHETIC
    report = {'schema_version': 'cantoai-external-result-v1', 'reference_origin': ORIGIN,
        'run_kind': SYNTHETIC if synthetic else 'EXTERNAL_PUBLISHED_REFERENCE_MODEL_RESULT',
        'is_model_result': not synthetic, 'split': config['split'], 'reference_field': p['reference_field'],
        'coverage': {'references': len(gold), 'source_text_groups': len({g['source_group'] for g in gold}),
                     'predictions_per_system': {s: len(v) for s, v in pred.items()}, 'dropped_rows': 0,
                     'duration_seconds': sum(r['duration_seconds'] for r in rows if ROLES[r['evaluation_role']][1] == config['split'])},
        'metrics': metrics, 'limitations': meta['limitations'], 'overlap': meta['overlap'],
        'freeze_verified': config['split'] == 'test', 'freeze_timing_independently_verified': False,
        'provenance_limit': 'Metadata binds local files, not proof of how predictions were generated or when a freeze occurred.',
        'audio_access': 'No audio opened by evaluator; receipt verification only.'}
    files = {'report.json': jbytes(report), 'per_utterance.jsonl': lbytes(per),
             'config.json': config_bytes, 'normalization.json': jbytes(p),
             'prediction_metadata.json': pm_bytes}
    if freeze_path:
        files['test_freeze.json'] = freeze_bytes
    manifest = {'created_utc': now(), 'engine_hashes': engine_hashes(), 'bundle_lock_sha256': bundle_sha,
        'predictions_sha256': sha(pb), 'prediction_metadata_sha256': sha(pm_bytes),
        'run_kind': report['run_kind'], 'output_hashes': {n: sha(b) for n, b in files.items()}}
    files['run_manifest.json'] = jbytes(manifest)
    write_files(out, files)
    return report

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    for name in ('reference-dir', 'audio-dir', 'out'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--reference-field', choices=['transcription', 'raw_transcription'], required=True)
    p.add_argument('--secondary-filter', choices=['off', 'unicode-punctuation-whitespace-v1'], default='off')
    v = sub.add_parser('validate'); v.add_argument('--bundle', required=True)
    f = sub.add_parser('freeze')
    for name in ('bundle', 'config', 'output'):
        f.add_argument('--' + name, required=True)
    f.add_argument('--declare-before-test-predictions', action='store_true')
    r = sub.add_parser('run')
    for name in ('bundle', 'config', 'predictions', 'prediction-metadata', 'out'):
        r.add_argument('--' + name, required=True)
    r.add_argument('--freeze')
    for command in (p, v, f, r):
        command.add_argument('--source-pins', required=True, help='Independently trusted local pin file; never inferred from the bundle')
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            prepare(args.reference_dir, args.audio_dir, args.out, args.reference_field, args.secondary_filter, args.source_pins)
            print('External-reference bundle prepared; no predictions or audio read, no model run.')
        elif args.command == 'validate':
            rows, audio, _, _, digest = load_bundle(args.bundle, args.source_pins)
            print(json.dumps({'reference_count': len(rows), 'receipt_count': len(audio), 'bundle_lock_sha256': digest, 'audio_opened': False}))
        elif args.command == 'freeze':
            freeze(args.bundle, args.config, args.output, args.declare_before_test_predictions, args.source_pins)
            print('Test/model/evaluator freeze saved; timing is an operator attestation only.')
        else:
            report = run(args.bundle, args.config, args.predictions, args.prediction_metadata, args.out, args.freeze, args.source_pins)
            print(report['run_kind'])
        return 0
    except (Error, OSError, KeyError, TypeError, ValueError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
