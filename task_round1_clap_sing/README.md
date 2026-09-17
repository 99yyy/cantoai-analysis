# ROUND-1 stage-2: CLAP `clap_sing` (scripts only)

Zero-shot LAION-CLAP scores on window FLAC files, then Spearman / `flag_sing` summaries. **Uncalibrated.** This package does not record analysis conclusions.

Model: `laion/larger_clap_music_and_speech`  
Prompts: `a person singing` / `a person speaking`  
Device: **CPU only**

## Weight size (download abort >2GB)

Hub listing of `laion/larger_clap_music_and_speech` (`main`, queried 2026-09-17):

| File | Bytes |
|---|---:|
| `pytorch_model.bin` | 776,444,665 |
| tokenizer + config + card | ~3,371,245 |
| **total** | **779,815,910 (~744 MiB)** |

This is **under 2GB**. The script still queries Hub blob sizes before `from_pretrained` and **aborts without downloading** if the estimate exceeds 2 GiB (`MAX_WEIGHT_BYTES`). `--help`, `--summarize`, `--dry-run`, and `--self-test` never load weights.

## Self-test (no audio, no weights)

From this directory. `pandas` / `numpy` / `scipy` are enough (see repo-root `requirements.txt`).

```bash
python scripts/run_clap_sing.py --help

python scripts/run_clap_sing.py --summarize \
  --clap-csv fixtures/clap_tiny.csv \
  --quality-csv fixtures/quality_with_flags_tiny.csv \
  --artifacts-dir /tmp/round1_clap/artifacts \
  --status-json /tmp/round1_clap/STATUS.json

python scripts/run_clap_sing.py --dry-run --limit 8 \
  --quality-csv fixtures/quality_with_flags_tiny.csv \
  --out /tmp/round1_clap/window_clap_sing.csv \
  --artifacts-dir /tmp/round1_clap/artifacts \
  --status-json /tmp/round1_clap/STATUS.json

python scripts/run_clap_sing.py --self-test
```

`--quality-csv` must include `window_id`, `singing_prob`, and `flag_sing`. Passing bare `window_quality.csv` exits with an error.

`--check-weights` queries Hub metadata only (no `pytorch_model.bin` download).

## Inference (audio worker)

`--quality-csv` **must** be the with_flags file (has `flag_sing` + `singing_prob`). Runtime paths below match `rounds/ROUND-1.md`; pass whatever the execution host uses.

```bash
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 1) smoke (limit) — writes CSV, both JSON artifacts, STATUS.json smoke_ok=true
python scripts/run_clap_sing.py \
  --windows-dir /workspace/cantoai/corpus/dataset_v2/work/windows \
  --quality-csv /workspace/cantoai/analysis/task2_window_quality/window_quality_with_flags.csv \
  --out /workspace/cantoai/analysis/ROUND-1/window_clap_sing.csv \
  --artifacts-dir /workspace/cantoai/analysis/ROUND-1/artifacts \
  --limit 20

# 2) summarize only (same entrypoint)
python scripts/run_clap_sing.py --summarize \
  --clap-csv /workspace/cantoai/analysis/ROUND-1/window_clap_sing.csv \
  --quality-csv /workspace/cantoai/analysis/task2_window_quality/window_quality_with_flags.csv \
  --artifacts-dir /workspace/cantoai/analysis/ROUND-1/artifacts
```

Full run: drop `--limit` only after smoke JSON keys exist and `STATUS.json` has `"smoke_ok": true`.

## Outputs

CSV columns: `window_id,clap_sing,clap_speak,clap_logit_diff,clap_ok,error`

- `clap_sing` / `clap_speak`: CLAP `logits_per_audio` for the two prompts
- `clap_logit_diff`: `clap_sing - clap_speak`
- `clap_ok`: `1` on success

`artifacts/corr_summary.json`: `spearman_clap_vs_panns`, `n_paired`  
Pairing: `clap_ok=1` inner-joined to the quality CSV on `window_id`; `n_paired` is that row count. Spearman uses `clap_sing` vs `singing_prob`.

`artifacts/flag_sing_contrast.json`: `median_clap_flag1`, `median_clap_flag0`, `n_flag1`, `n_flag0`, plus `mw_pvalue` (Mann–Whitney greater) when `n_flag1>=10`, or `median_diff` + `bootstrap_ci_low` / `bootstrap_ci_high` / `bootstrap_n` when `n_flag1<10`.

`STATUS.json` (default: parent of `--artifacts-dir`): includes `"smoke_ok": true` after a successful summarize.
