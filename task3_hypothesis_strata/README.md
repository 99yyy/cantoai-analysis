# Task 3: Stratified Hypothesis Analysis

Stratified agreement analysis comparing **film** (電影口白) vs **contemporary-only** content, with bootstrap confidence intervals.

## Quick Start (Sample Data)

Uses the Cloud Agent fixture in `fixtures/sample.sqlite` (see `SCHEMA.md`).

```bash
cd /workspace
python3 task3_hypothesis_strata/scripts/run_hypothesis_strata.py \
    --db fixtures/sample.sqlite \
    --quality fixtures/sample_window_quality.csv \
    --multilabel task3_multilabel_flags/video_multilabel_flags.csv \
    --out task3_hypothesis_strata/_sample_out \
    --seed 0 --bootstrap 200

python3 task3_hypothesis_strata/scripts/check_sample_outputs.py \
    --out task3_hypothesis_strata/_sample_out

python3 task3_hypothesis_strata/scripts/test_jyutping_parse.py
```

## Full Data Usage

```bash
python task3_hypothesis_strata/scripts/run_hypothesis_strata.py \
    --db /path/to/corpus.sqlite \
    --quality task2_window_quality/window_quality.csv \
    --multilabel task3_multilabel_flags/video_multilabel_flags.csv \
    --out task3_hypothesis_strata/output \
    --seed 0 --bootstrap 2000
```

## CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--db` | Yes | - | Path to SQLite database |
| `--quality` | Yes | - | Path to window_quality.csv (columns: `window_id`, `music_prob`, `singing_prob`, `snr_db`, `dnsmos_ovrl`) |
| `--multilabel` | Yes | - | Path to video_multilabel_flags.csv (columns include `film_flag`, `contemporary_only`) |
| `--out` | Yes | - | Output directory |
| `--seed` | No | 0 | Random seed for reproducible bootstrap |
| `--bootstrap` | No | 2000 | Number of bootstrap iterations (use 200 for quick testing) |
| `--tiers` | No | A B | Tiers to include (space-separated) |

## Output Files

| File | Description |
|------|-------------|
| `agreement_by_onset.csv` | Stratified by initial consonant (声母): n-, l-, ng-, zero, gw-/kw-, g-/k-, other |
| `agreement_by_coda.csv` | Stratified by coda (韵尾): -n, -ng, -t, -k, -p, -m, open |
| `agreement_by_tone.csv` | Stratified by dictionary tone 1–6 |
| `agreement_by_snr.csv` | Stratified by SNR: <5, 5–10, 10–15, 15–20, >20 dB |
| `agreement_by_singing.csv` | Stratified by singing_prob: <0.2, 0.2–0.5, >0.5 |
| `agreement_by_rate.csv` | Stratified by speech rate (chars_per_sec): <3, 3–5, 5–7, >7 |
| `tone1_confusion.csv` | Tone 1 → 4/6 confusion rates |
| `summary_contrast.csv` | Aggregate contrasts for hypothesis A/B/C |

## Output Column Schema

Each stratification file contains:

| Column | Description |
|--------|-------------|
| `subset` | `film` or `contemporary` |
| `bin` | Stratum label (e.g., "n-", "<5", "1") |
| `n_syllables` | Number of syllables in stratum |
| `n_videos` | Number of unique videos in stratum |
| `agree_syl` | Syllable-weighted agreement rate |
| `agree_syl_ci_low` | 95% CI lower bound (bootstrap by video) |
| `agree_syl_ci_high` | 95% CI upper bound |
| `agree_video_median` | Median per-video agreement rate |
| `agree_video_median_ci_low` | 95% CI lower bound |
| `agree_video_median_ci_high` | 95% CI upper bound |

## Definitions

### Agreement
A syllable is in **agreement** if `jp_match ∈ {exact_default, exact_alt}`.

### Subsets
- **Film** (電影口白): `film_flag = 1` (video-level flag)
- **Contemporary**: `contemporary_only = 1`

### Film Dialogue (window-level)
For certain analyses, "film dialogue" = film subset windows with `singing_prob < 0.2`.

### Bootstrap CI
95% confidence intervals computed by resampling videos with replacement (B iterations, default 2000).

## Stratification Axes

### a. Initial Consonant (声母)
Parsed from `jp_default` (dictionary reading):
- **n-**: 泥母 (nasal n)
- **l-**: 來母 (lateral l)
- **ng-**: 疑母 (velar nasal)
- **zero**: 零声母 (vowel/glide initial)
- **gw-/kw-**: 合口見組 (labialized velars)
- **g-/k-**: 見組 (velars)
- **other**: all other initials

### b. Coda (韵尾)
- **-n, -ng**: Nasal codas
- **-t, -k, -p**: Stop codas (入声)
- **-m**: Nasal coda (rare)
- **open**: No coda

### c. Dictionary Tone
Tones 1–6 from `jp_default`.

Additional output: Tone 1 heard as Tone 4 or 6 rate (from `jp_realized`).

### d. SNR Bins (dB)
`<5`, `5–10`, `10–15`, `15–20`, `>20`

### e. Singing Probability Bins
`<0.2`, `0.2–0.5`, `>0.5`

### f. Speech Rate Bins (chars_per_sec)
`<3`, `3–5`, `5–7`, `>7`

## Summary Contrasts

`summary_contrast.csv` includes:
1. Film agreement before/after removing `singing_prob > 0.5` windows
2. High-SNR (>15 dB) film dialogue vs contemporary for n-/ng-/gw- initials
3. Overall film vs contemporary comparison

## Dependencies

See `requirements.txt`. Compatible with repository root `requirements.txt`.

## Notes

- Script is read-only on input data.
- Bootstrap seed is fixed for reproducibility.
- Large bootstrap counts (2000) may take several minutes on full data.
