# ROUND-2 stage-2: stratified listening sheet (scripts only)

Build a clap×PANNs quartile-cross sample for human annotation. **Uncalibrated scores.** This package does not record analysis conclusions.

Labels are filled later by Tom. The sampler writes `human_label=unset`.

## Self-test (no audio)

From this directory. `pandas` / `numpy` are enough (see repo-root `requirements.txt`).

```bash
python scripts/build_listening_sheet.py --help

python scripts/build_listening_sheet.py \
  --clap-csv fixtures/clap_tiny.csv \
  --quality-csv fixtures/quality_with_flags_tiny.csv \
  --var-csv fixtures/var_tiny.csv \
  --flags-csv fixtures/window_flags_tiny.csv \
  --out-dir /tmp/round2-smoke \
  --n-total 200 --n-film 160 --n-contemporary 40 --seed 20260918 \
  --limit 50

python scripts/build_listening_sheet.py --self-test
```

`--flags-csv` must be **window-level** `window_multilabel_flags.csv` (`window_id`, `video_id`, `film_flag`). Passing `video_multilabel_flags.csv` exits with an error.

`--quality-csv` must include `singing_prob` and `flag_sing`. Passing bare `window_quality.csv` exits with an error.

Quartiles (`q1_clap`, `q3_clap`, `q1_panns`, `q3_panns`) are computed on the **full** joinable set (`clap_ok=1` ∩ quality ∩ flags ∩ var) **before** sampling. `--limit N` only caps sample size (and scales `n_film` / `n_contemporary`).

`flag_sing=1` rule A: every joinable flagged window is forced into the sheet and counts toward `n_total` (`forced_in_quota: true`).

## Full sample (after smoke_ok)

Runtime paths match `rounds/ROUND-2.md`; pass whatever the execution host uses.

```bash
python scripts/build_listening_sheet.py \
  --clap-csv /workspace/cantoai/analysis/ROUND-1/window_clap_sing.csv \
  --quality-csv /workspace/cantoai/analysis/task2_window_quality/window_quality_with_flags.csv \
  --var-csv /workspace/cantoai/analysis/task_calib_demucs_var/window_var_db.csv \
  --flags-csv /workspace/cantoai/analysis/task3_multilabel_flags/window_multilabel_flags.csv \
  --out-dir /workspace/cantoai/analysis/ROUND-2 \
  --n-total 200 --n-film 160 --n-contemporary 40 --seed 20260918
```

Drop `--limit` only after fixtures/`--limit` smoke writes `STATUS.json` with `"smoke_ok": true` and a mini sheet with ≥1 row, all `human_label=unset`.

## Summarize labels (reserved; after annotation)

```bash
python scripts/build_listening_sheet.py --summarize-labels \
  --sheet /workspace/cantoai/analysis/ROUND-2/listening_sheet.csv \
  --manifest /workspace/cantoai/analysis/ROUND-2/sample_manifest.json \
  --out-dir /workspace/cantoai/analysis/ROUND-2/metrics
```

Writes `label_by_quadrant.json`, `single_track_gap.json`, `label_by_film.json`.

- `singing_rate` := `mean(human_label == "singing")` among `human_label != "unset"` (does not count `mixed`)
- `recitation_or_mixed_rate` := `mean(human_label in {"recitation","mixed"})` among labeled rows

## Outputs

`listening_sheet.csv` columns: `window_id,video_id,film_flag,clap_sing,singing_prob,var_db,stratum,human_label,annotator_note,forced_flag_sing`

Strata (quartile cross, not 3×3): `both_high`, `both_low`, `panns_high_only`, `clap_high_only`, `mid`.

`sample_manifest.json` includes at least: `seed,n_total,n_film,n_contemporary,q1_clap,q3_clap,q1_panns,q3_panns,stratum_quotas,window_ids,forced_flag_sing_ids,forced_in_quota`

`STATUS.json` includes `"smoke_ok"` (bool).

Defaults: `n_total=200`, `n_film=160`, `n_contemporary=40`, `seed=20260918`. If a film/contemporary pool is smaller than its target, the group is shrunk to the pool and stratum quotas are split equally across the five layers (remainder to the corner strata first).
