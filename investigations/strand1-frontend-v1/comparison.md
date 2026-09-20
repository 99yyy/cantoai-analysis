# Win / Lose / Tie vs ToJyutping (jp_ctx)

Label evidence is **only** the acoustic model (`jp_realized`).
Strongest claim: **"on these rows I beat ToJyutping at predicting realized reading"** — not "my reading is correct".

## Split

| item | count |
|---|---|
| n_judgeable | 139362 |
| n_videos_total | 565 |
| n_videos_train_hash | 388 |
| n_videos_eval_hash | 177 |
| n_overlap_text_clean | 62 |
| n_rows_moved_eval_to_train | 3430 |
| n_train | 100604 |
| n_eval | 38758 |
| n_videos_train_final | 565 |
| n_videos_eval_final | 171 |
| n_text_clean_train | 2438 |
| n_text_clean_eval | 989 |
| eval_should_change | 8051 |
| eval_should_not | 30707 |

Rules: 280 trigrams (support≥3), 124 left-bigrams, 109 right-bigrams (lift-gated over jp_ctx; unigrams disabled).

## C. Among rows where pred ≠ jp_ctx

| outcome | n | meaning |
|---|---|---|
| **true_win** | 474 | pred==realized and jp_ctx!=realized |
| **true_lose** | 164 | jp_ctx==realized and pred!=realized |
| tie_both_wrong | 99 | pred≠realized and ctx≠realized |
| tie_both_right | 0 | (rare if pred≠ctx) |
| **n_pred_ne_ctx** | 737 | total overrides |

### Also: rows left unchanged (pred == jp_ctx)

| outcome | n |
|---|---|
| same_both_right | 31313 |
| same_both_wrong | 6708 |

## A. Exact-match vs jp_realized

| stratum | n | pred EM | ToJyutping (ctx) EM | Δ |
|---|---|---|---|---|
| all judgeable eval | 38758 | 0.82014 | 0.812142 | 0.007998 |
| ctx = default | 37011 | 0.827024 | 0.821729 | 0.005296 |
| ctx ≠ default | 1747 | 0.674299 | 0.609044 | 0.065255 |
| should change (realized≠default) | 8051 | 0.181344 | 0.132157 | 0.049186 |
| should not (realized=default) | 30707 | 0.987625 | 0.990426 | -0.002801 |

## B. Binary “change from default?” (among ctx=default)

- Base rate (realized≠default | ctx=default): **0.178271**
- Precision / Recall / F1: **0.736264** / **0.060928** / **0.112542**
- Always-predict-change baseline F1: **0.302598** (P=0.178271, R=1)
- Confusion: TP=402 FP=144 FN=6196 TN=30269

## D. Tone-only vs segment among true wins

- Tone-only wins: 294
- Segment-different wins: 180
