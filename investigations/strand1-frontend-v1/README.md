# strand1-frontend-v1 — context-aware Jyutping vs ToJyutping

Exploratory campaign notes. This folder is **not** a TASK brief: declared
numbers, SQL, and `results.json` / `mine.json` still belong under `tasks/`.

## Hard limit (do not soften)

on these rows I beat ToJyutping at predicting realized reading — NOT “my reading is correct”. Label evidence is ONLY the acoustic model (`jp_realized`).

## Corrected reachable definition

`metrics.json` is the original v1 snapshot (exact string equality vs `jp_realized`).

**`metrics_exact_alt.json` is the corrected reachable definition** (a prediction
may count as reachable when it matches an alternate dictionary reading, not only
the acoustic string). Prefer that file when it is present. It is **not** in this
tree yet; see TODO below. Do not treat `metrics.json` as that corrected
definition.

## Corpus pin

- Path: `data/corpus_v2.sqlite` (opened read-only)
- sha256: `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f`
- `run.py` hashes the file and compares it to this pin **and** the sha256 in
  the repository `README.md`. On mismatch it prints both values and exits
  non-zero. The sqlite file is not modified.

## Reproduce

From the repository root (no `.venv` is committed):

```bash
python3 investigations/strand1-frontend-v1/run.py --check
```

`--check` recomputes the original v1 numbers against the pinned corpus and
compares them to committed `metrics.json` (ignores `tojyutping_spot_check`,
which needs the optional package). It does not overwrite the v1 snapshot files.

Write a fresh copy (does not replace the committed snapshot unless `--out-dir`
points at this folder):

```bash
python3 investigations/strand1-frontend-v1/run.py --out-dir /tmp/strand1-frontend-v1-rerun
```

Regenerate `predictions_eval.csv` (not committed; see below):

```bash
python3 investigations/strand1-frontend-v1/run.py --out-dir /tmp/strand1-frontend-v1-rerun --write-predictions
```

Optional ToJyutping spot-check only:

```bash
pip install -r investigations/strand1-frontend-v1/requirements.txt
```

Eval still uses `jp_ctx` from the database. The package is not required to
reproduce the v1 metrics.

## Method (original v1)

1. Judgeable rows: `tier IN ('A','B') AND jp_realized IS NOT NULL AND dur>0 AND jp_ctx IS NOT NULL AND jp_default IS NOT NULL`.
2. Split videos ~70/30 train/eval by `md5(video_id) % 100`; any `text_clean` appearing in both → all copies moved to train.
3. On train, learn lift-gated `(left,char,right)` / bigram → majority `jp_realized` (support≥3, majority must beat keeping `jp_ctx` on that pattern). Unigrams are disabled in this refined v1 (`n_unigrams=0`).
4. Inference: start from `jp_ctx` (ToJyutping); if a trigram rule fires, use it; else if a left/right bigram rule fires, use it; else keep `jp_ctx`.
5. Opponent is ToJyutping (`jp_ctx`), not “always default”.

The sampling frame is the judgeable A+B rows that also have non-null `jp_ctx`
and `jp_default`. `dur > 0` is declared here and removes the known
zero-duration aligner rows (contract clause 25). This is not a TASK
measurement loop.

## Original v1 headline numbers (eval)

Copied from the v1 snapshot (`metrics.json` / `comparison.md`); not re-judged
here:

- Base rate among ctx=default judgeable eval: **17.8%** realized≠default
- Change-decision F1 (among ctx=default): **0.1125** (P=0.7363, R=0.0609); always-change baseline F1=0.3026
- Exact-match all eval: pred **0.8201** vs ctx **0.8121** (Δ=+0.0080)
- Overrides pred≠ctx: true_win=474, true_lose=164, tie_both_wrong=99 (n_diff=737)
- Rules learned: 280 trigrams, 124+109 bigrams; train=100604, eval=38758

Recommendation in the snapshot: **DO NOT CONTINUE** — directionally positive
but effect size too small on this corpus to justify a product line.

## Files

| file | what |
|---|---|
| `run.py` | recompute original v1 against `data/corpus_v2.sqlite` |
| `metrics.json` | original v1 metrics snapshot |
| `comparison.md` | original v1 win/lose/tie write-up |
| `rules.json` | learned trigram/bigram rules |
| `predictions_eval.csv` | eval-row predictions (~2.0 MB); regenerate with `--write-predictions` |
| `requirements.txt` | optional ToJyutping |

`predictions_eval.csv` is under 25 MB so it is committed. Regenerate:

```bash
python3 investigations/strand1-frontend-v1/run.py --out-dir /tmp/strand1-frontend-v1-rerun --write-predictions
```

## TODO (uploads incomplete)

Parent uploads did not include these files. **Do not invent numbers.** Parent
will reply with the files:

- `metrics_exact_alt.json` — corrected reachable definition (missing)
- `comparison_exact_alt.md` — missing
- `base_rate_note.md` — missing
