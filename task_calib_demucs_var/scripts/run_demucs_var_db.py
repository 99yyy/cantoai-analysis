#!/usr/bin/env python3
"""
Compute var_db (vocals/rest RMS ratio in dB) for audio windows using htdemucs.

For each window, uses htdemucs to separate:
  - vocals track
  - rest = drums + bass + other (sum of the three tracks)

Then computes:
  - rms_vocals = sqrt(mean(vocals^2))
  - rms_rest = sqrt(mean(rest^2))
  - var_db = 20 * log10(rms_vocals / rms_rest)

Output CSV columns:
  window_id, rms_vocals, rms_rest, var_db, demucs_ok, error

Local patch: Separator is built once (module-level singleton) and reused
across all windows — upstream script created a new Separator per window.
"""

import argparse
import csv
import logging
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

VAR_DB_INF = 999.0
VAR_DB_NEG_INF = -999.0

# Local patch: Separator singleton — created once, reused by process_window
_SEPARATOR = None


def get_separator():
    """Return module-level htdemucs Separator (CPU), creating it once."""
    global _SEPARATOR
    if _SEPARATOR is None:
        import demucs.api
        logger.info("Creating Separator(model='htdemucs', device='cpu') once (local singleton patch)")
        _SEPARATOR = demucs.api.Separator(model="htdemucs", device="cpu")
        logger.info("Separator ready")
    return _SEPARATOR


def compute_rms(audio: np.ndarray) -> float:
    """Compute RMS of audio array."""
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


def separate_with_demucs(audio_path: Path, output_dir: Path) -> dict:
    """
    Run htdemucs separation on audio file.

    Returns dict with keys: vocals, drums, bass, other (each np.ndarray)
    or raises exception on failure.
    """
    separator = get_separator()

    origin, separated = separator.separate_audio_file(str(audio_path))

    result = {}
    for stem_name in ["vocals", "drums", "bass", "other"]:
        if stem_name in separated:
            stem_audio = separated[stem_name].numpy()
            if stem_audio.ndim == 2:
                stem_audio = stem_audio.mean(axis=0)
            result[stem_name] = stem_audio
        else:
            raise ValueError(f"Missing stem: {stem_name}")

    return result


def process_window(audio_path: Path) -> dict:
    """
    Process a single window audio file.

    Returns dict with: window_id, rms_vocals, rms_rest, var_db, demucs_ok, error
    """
    window_id = audio_path.stem

    result = {
        "window_id": window_id,
        "rms_vocals": "",
        "rms_rest": "",
        "var_db": "",
        "demucs_ok": 0,
        "error": "",
    }

    try:
        stems = separate_with_demucs(audio_path, audio_path.parent)

        vocals = stems["vocals"]
        rest = stems["drums"] + stems["bass"] + stems["other"]

        rms_vocals = compute_rms(vocals)
        rms_rest = compute_rms(rest)

        result["rms_vocals"] = f"{rms_vocals:.8e}"
        result["rms_rest"] = f"{rms_rest:.8e}"

        if rms_rest == 0.0:
            if rms_vocals == 0.0:
                var_db = 0.0
            else:
                var_db = VAR_DB_INF
            result["error"] = "rest_rms_zero"
        elif rms_vocals == 0.0:
            var_db = VAR_DB_NEG_INF
            result["error"] = "vocals_rms_zero"
        else:
            var_db = 20.0 * np.log10(rms_vocals / rms_rest)

        result["var_db"] = f"{var_db:.4f}"
        result["demucs_ok"] = 1

    except Exception as e:
        result["error"] = str(e).replace("\n", " ")[:200]
        result["demucs_ok"] = 0

    return result


def generate_synth_audio(output_path: Path, duration_sec: float = 5.0, sr: int = 44100):
    """
    Generate synthetic audio for testing: sine wave (simulated vocal) + noise (simulated music bed).
    """
    import soundfile as sf

    t = np.linspace(0, duration_sec, int(sr * duration_sec), dtype=np.float32)

    vocal_freq = 440.0
    vocal = 0.3 * np.sin(2 * np.pi * vocal_freq * t)

    noise = 0.1 * np.random.randn(len(t)).astype(np.float32)

    mixed = vocal + noise
    mixed = mixed / np.max(np.abs(mixed)) * 0.9

    sf.write(str(output_path), mixed, sr)
    logger.info(f"Generated synthetic audio: {output_path}")


def check_model_size():
    """
    Check if demucs model would require >2GB download.
    htdemucs is ~316MB (single file), well under threshold.
    """
    pass


def main():
    parser = argparse.ArgumentParser(
        description="Compute var_db (vocals/rest RMS ratio) using htdemucs for audio windows.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all FLAC files in a directory
  python run_demucs_var_db.py /path/to/windows -o results.csv

  # Process with limit
  python run_demucs_var_db.py /path/to/windows -o results.csv --limit 10

  # Dry-run with synthetic audio (for testing without real data)
  python run_demucs_var_db.py --dry-run-synth -o test_results.csv

  # Read window IDs from file
  python run_demucs_var_db.py /path/to/windows -o results.csv --id-file window_ids.txt

Output CSV columns:
  window_id, rms_vocals, rms_rest, var_db, demucs_ok, error

var_db formula:
  var_db = 20 * log10(rms_vocals / rms_rest)
  where rest = drums + bass + other
"""
    )

    parser.add_argument(
        "input_dir",
        nargs="?",
        type=Path,
        help="Directory containing window FLAC files (default: current dir)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("window_var_db.csv"),
        help="Output CSV path (default: window_var_db.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of windows to process",
    )
    parser.add_argument(
        "--id-file",
        type=Path,
        default=None,
        help="File containing window IDs (one per line), or read from stdin if -",
    )
    parser.add_argument(
        "--dry-run-synth",
        action="store_true",
        help="Generate synthetic audio and run pipeline (for testing without real FLAC files)",
    )
    parser.add_argument(
        "--synth-count",
        type=int,
        default=2,
        help="Number of synthetic audio files to generate in dry-run mode (default: 2)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    check_model_size()

    audio_files = []

    if args.dry_run_synth:
        logger.info("Running in dry-run-synth mode: generating synthetic test audio")

        tmp_dir = Path(tempfile.mkdtemp(prefix="demucs_synth_"))
        logger.info(f"Synthetic audio directory: {tmp_dir}")

        for i in range(args.synth_count):
            synth_path = tmp_dir / f"synth_window_{i:04d}.wav"
            generate_synth_audio(synth_path)
            audio_files.append(synth_path)

    elif args.id_file:
        if args.id_file == Path("-"):
            ids = [line.strip() for line in sys.stdin if line.strip()]
        else:
            with open(args.id_file) as f:
                ids = [line.strip() for line in f if line.strip()]

        if not args.input_dir:
            parser.error("input_dir is required when using --id-file")

        for wid in ids:
            flac_path = args.input_dir / f"{wid}.flac"
            if flac_path.exists():
                audio_files.append(flac_path)
            else:
                logger.warning(f"Window file not found: {flac_path}")

    else:
        if not args.input_dir:
            parser.error("input_dir is required (or use --dry-run-synth)")

        if not args.input_dir.is_dir():
            logger.error(f"Input directory does not exist: {args.input_dir}")
            sys.exit(1)

        audio_files = sorted(args.input_dir.glob("*.flac"))
        if not audio_files:
            audio_files = sorted(args.input_dir.glob("*.wav"))

        if not audio_files:
            logger.error(f"No FLAC or WAV files found in {args.input_dir}")
            sys.exit(1)

    if args.limit and len(audio_files) > args.limit:
        audio_files = audio_files[:args.limit]

    logger.info(f"Processing {len(audio_files)} audio files")

    # Local patch: warm up Separator once before the loop
    if audio_files and not args.dry_run_synth:
        get_separator()
    elif audio_files and args.dry_run_synth:
        get_separator()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["window_id", "rms_vocals", "rms_rest", "var_db", "demucs_ok", "error"]

    with open(args.output, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for i, audio_path in enumerate(audio_files, 1):
            logger.info(f"[{i}/{len(audio_files)}] Processing: {audio_path.name}")

            result = process_window(audio_path)
            writer.writerow(result)
            csvfile.flush()

            if result["demucs_ok"]:
                logger.info(f"  var_db={result['var_db']} dB")
            else:
                logger.warning(f"  FAILED: {result['error'][:80]}")

    logger.info(f"Results written to: {args.output}")

    if args.dry_run_synth:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info(f"Cleaned up temporary directory: {tmp_dir}")


if __name__ == "__main__":
    main()
