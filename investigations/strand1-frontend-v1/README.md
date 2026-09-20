# strand1-frontend-v1 — context-aware Jyutping vs ToJyutping

Exploratory campaign notes. This folder is **not** a TASK brief: declared
numbers, SQL, and `results.json` / `mine.json` still belong under `tasks/`.

## Hard limit (do not soften)

on these rows I beat ToJyutping at predicting realized reading — NOT “my reading is correct”. Label evidence is ONLY the acoustic model (`jp_realized`).

## Corrected reachable definition

**`metrics_exact_alt.json` is the corrected reachable (exact_alt) change-decision metrics.** Prefer it over `metrics.json` for any claim about “should we change from default?”.

Among `jp_ctx == jp_default`:

- Positive label: `jp_match == 'exact_alt'` (realized is another dictionary candidate — reachable for a dict-alt override).
- Predicted change: `pred != jp_default`.
- `tone` / `segment` / `diff` are unreachable for that override and are not the positive class.

`metrics.json` remains the original v1 snapshot (positive class = realized≠default; exact string equality vs `jp_realized`). Do not treat it as the reachable definition.

Write-up: `comparison_exact_alt.md`. Why README 17.8% ≠ split-table 20.8%: `base_rate_note.md` (different denominators, not a corpus bug).

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

The exact_alt rescore in `metrics_exact_alt.json` / `comparison_exact_alt.md`
uses the same v1 rules and eval split (preds from `rules.json`). `run.py`
reproduces the original v1 snapshot, not a second exact_alt writer.

Write a fresh copy of the original v1 snapshot:

```bash
python3 investigations/strand1-frontend-v1/run.py --out-dir /tmp/strand1-frontend-v1-rerun
```

Regenerate `predictions_eval.csv`:

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

## Headline numbers

Original v1 (`metrics.json` / `comparison.md`), not the reachable definition:

- Base rate among ctx=default judgeable eval: **17.8%** realized≠default (see `base_rate_note.md` for vs 20.8%)
- Change-decision F1 (among ctx=default, old label): **0.1125** (P=0.7363, R=0.0609); always-change baseline F1=0.3026
- Exact-match all eval: pred **0.8201** vs ctx **0.8121** (Δ=+0.0080)
- Overrides pred≠ctx: true_win=474, true_lose=164, tie_both_wrong=99 (n_diff=737)
- Rules learned: 280 trigrams, 124+109 bigrams; train=100604, eval=38758

Corrected reachable change-decision (`metrics_exact_alt.json` / `comparison_exact_alt.md`), among eval `jp_ctx==jp_default`:

- Positive class `jp_match==exact_alt`; base rate **3.6%** (1333/37011)
- F1 **0.2363** (P=0.4066, R=0.1665); always-change F1=0.0695
- Confusion: TP=222 FP=324 FN=1111 TN=35354
- True reachable recall 16.7% (222/1333). Tom’s old_TP/n_exact_alt ≈ 30.2% overcounts because 180 of 402 old TPs are tone/segment/diff.

Recommendation in both snapshots: **DO NOT CONTINUE** — still directionally positive (win 474>164, EM Δ=+0.0080) but coverage of reachable alts and EM lift remain too small for a product line.

## Files

| file | what |
|---|---|
| `run.py` | recompute original v1 against `data/corpus_v2.sqlite` |
| `metrics.json` | original v1 metrics snapshot |
| `metrics_exact_alt.json` | **corrected reachable (exact_alt) change-decision metrics** |
| `comparison.md` | original v1 win/lose/tie write-up |
| `comparison_exact_alt.md` | reachable exact_alt rescore write-up |
| `base_rate_note.md` | 17.8% vs 20.8% denominators |
| `rules.json` | learned trigram/bigram rules |
| `predictions_eval.csv` | eval-row predictions (~2.0 MB); regenerate with `--write-predictions` |
| `requirements.txt` | optional ToJyutping |
