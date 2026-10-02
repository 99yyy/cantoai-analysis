"""Invented fixtures only. Receipt fields simulate a decoder; no WAV exists."""
from pathlib import Path
import adapter as a


def build_fixture(root):
    root = Path(root)
    rows, audio = [], []
    for index in range(30):
        role, split, directory = ('dev_smoke', 'validation', 'dev') if index < 10 else ('heldout_smoke', 'test', 'test')
        basename = f'synthetic_only_{index}.wav'
        uid = f'fleurs:yue_hant_hk:{split}:{1000000000 + index}:{basename}'
        raw = f'SYNTHETIC RAW TEXT {index}!'
        norm = f'synthetic normalized text {index}'
        row = {'sample_id': uid, 'dataset': 'google/fleurs', 'config': 'yue_hant_hk',
            'dataset_revision': a.REVISION, 'license': 'CC-BY-4.0', 'evaluation_role': role,
            'source_split': split, 'source_row_index': 1000000000 + index,
            'source_text_id': 1000000000 + index, 'source_audio_basename': basename,
            'source_snapshot_kind': 'SYNTHETIC_FIXTURE_NOT_PUBLISHED_DATA',
            'source_snapshot_sha256': a.sha(b'fabricated snapshot'),
            'raw_transcription': raw, 'raw_transcription_sha256': a.sha(raw.encode()),
            'transcription': norm, 'transcription_sha256': a.sha(norm.encode()),
            'reference_origin': 'official_human_read_prompt_reference_not_new_manual_transcription',
            'local_text_transformations': [], 'speaker_id': None, 'num_samples': 16000,
            'sampling_rate_hz': 16000, 'duration_seconds': 1.0,
            **{key: 'unknown' for key in a.OVERLAP}}
        receipt = {key: row[key] for key in ('sample_id', 'source_split', 'source_text_id',
            'source_audio_basename', 'evaluation_role', 'license', 'transcription_sha256',
            'raw_transcription_sha256') + a.OVERLAP}
        receipt.update(relative_audio_path=f'wav/{directory}/{basename}',
            audio_sha256=a.sha(f'NO AUDIO {index}'.encode()), audio_bytes=64044,
            decode_verified=True, decode_method='SYNTHETIC_NO_DECODING',
            measurements={'channels': 1, 'sampling_rate_hz': 16000, 'bits_per_sample': 32,
                'format_code': 3, 'sample_frames': 16000, 'duration_seconds': 1.0},
            ffprobe={'codec_name': 'pcm_f32le', 'channels': 1, 'sample_rate': '16000', 'duration_ts': 16000},
            listened_to=False, model_inference_performed=False)
        rows.append(row); audio.append(receipt)
    reference_bytes = a.lbytes(rows)
    reference_hash = a.sha(reference_bytes)
    for receipt in audio:
        receipt['reference_file_sha256'] = reference_hash
    audio_bytes = a.lbytes(audio)
    reference_files = {
        'reference_30.jsonl': reference_bytes,
        'dev_smoke.jsonl': a.lbytes(rows[:10]),
        'heldout_smoke.jsonl': a.lbytes(rows[10:]),
        'selection.json': a.jbytes({'selected': [
            {'sample_id': r['sample_id'], 'source_text_id': r['source_text_id'],
             'role': r['evaluation_role'], 'split': r['source_split']} for r in rows]}),
        'manifest.json': a.jbytes({'reference_file_sha256': reference_hash}),
        'license_evidence.json': a.jbytes({'kind': 'SYNTHETIC_NOT_LICENSE_EVIDENCE'}),
        'source_evidence.json': a.jbytes({'kind': 'SYNTHETIC_NOT_SOURCE_EVIDENCE'}),
    }
    audio_files = {'audio_manifest_30.jsonl': audio_bytes,
        'manifest.json': a.jbytes({'reference_file_sha256': reference_hash,
            'audio_manifest_sha256': a.sha(audio_bytes), 'all_decode_verified': True,
            'model_inference_count': 0}),
        'qa_report.json': a.jbytes({'kind': 'SYNTHETIC_NO_AUDIO_WAS_DECODED'})}
    pins = {'reference': {name: a.sha(data) for name, data in reference_files.items()},
            'audio': {name: a.sha(data) for name, data in audio_files.items()},
            'projection': {'source_records_sha256': a.sha(a.lbytes(rows)),
                           'audio_receipts_sha256': a.sha(a.lbytes(audio))}}
    reference_dir, audio_dir = root/'reference', root/'audio'
    a.write_files(reference_dir, reference_files)
    a.write_files(audio_dir, audio_files)
    pin_path = root/'trusted-pins.json'
    pin_path.write_bytes(a.jbytes(pins))
    bundle = root/'prepared'
    a.prepare(reference_dir, audio_dir, bundle, 'transcription', source_pins_path=pin_path)
    return bundle, pin_path, reference_dir, audio_dir
