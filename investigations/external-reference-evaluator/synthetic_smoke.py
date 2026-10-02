#!/usr/bin/env python3
"""Fabricated text only. Does not load the public reference bundle or any audio."""
import argparse
from pathlib import Path
import adapter as a


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    # Deliberately invented strings and IDs, not copies of public reference rows.
    gold = [{'utterance_id': 'synthetic_only_1', 'source_group': 'synthetic_group_a', 'reference': '甲乙'},
            {'utterance_id': 'synthetic_only_2', 'source_group': 'synthetic_group_b', 'reference': '丙丁戊己庚辛壬癸'}]
    predictions = {'SYNTHETIC_ONLY': {'synthetic_only_1': '甲丙', 'synthetic_only_2': '丙丁戊己庚辛壬癸'}}
    config = {'systems': ['SYNTHETIC_ONLY'], 'baseline': 'SYNTHETIC_ONLY', 'bootstrap': {'iterations': 0, 'seed': 17}}
    metrics, per = a.score_rows(gold, predictions, config, a.policy('transcription', 'off'))
    expected = {'N': 10, 'S': 1, 'D': 0, 'I': 0, 'E': 1, 'CER': 0.1}
    a.require(metrics['primary']['systems']['SYNTHETIC_ONLY'] == expected, 'synthetic arithmetic self-check failed')
    report = {'run_kind': a.SYNTHETIC, 'is_model_result': False,
              'reference_kind': 'FABRICATED_TEXT_NOT_FLEURS_NOT_HUMAN_GOLD',
              'public_reference_bundle_loaded': False, 'audio_opened': False,
              'model_inference_count': 0, 'expected_counts': expected, 'mechanical_metrics': metrics,
              'warning': 'This score tests software arithmetic only. It measures no model or benchmark.',
              'engine_hashes': a.engine_hashes()}
    a.write_files(args.out, {'synthetic_report.json': a.jbytes(report), 'synthetic_per_utterance.jsonl': a.lbytes(per)})
    print(a.SYNTHETIC)

if __name__ == '__main__':
    main()
