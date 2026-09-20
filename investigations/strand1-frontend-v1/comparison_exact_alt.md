# Reachable “should change” = `exact_alt` only (v1 rescore)

Corpus sha256 `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f` (verified). DB not modified.
Rescored **existing** v1 rules / same eval split (preds regenerated from `rules.json`; outcome counts match v1: win 474 / lose 164 / tie_wrong 99).

## Definition correction

Among `jp_ctx == jp_default`:

| bucket | meaning | reachable for dict-alt override? |
|---|---|---|
| `exact_default` | realized == default | should **NOT** change |
| `exact_alt` | realized is another dictionary candidate | **YES** — should change |
| `tone` / `segment` / `diff` | realized ≠ default but not a dict candidate | **NO** — unreachable |

Old “should change” = realized≠default. Cap: exact_alt is only **20.1%** of that bucket.

## 1. Overall counts (all judgeable, ctx=default)

| metric | n |
|---|---|
| n | 133340 |
| exact_default | 108785 |
| realized≠default | 24555 |
| exact_alt | 4930 |
| tone + segment + diff | 19625 (tone=10785, segment=7344, diff=1496) |
| exact_alt / old should-change | 4930/24555 = **0.2008** |

Tom’s counts verified.

## 2–3. Change-decision among eval `jp_ctx==jp_default` (n=37011)

Eval ctx=default `jp_match`: exact_alt=1333, exact_default=30413, tone=2982, segment=1935, diff=348.

| definition | positive label | TP | FP | FN | TN | P | R | F1 | base rate | always-change F1 |
|---|---|---|---|---|---|---|---|---|---|---|
| **NEW reachable** | `jp_match==exact_alt` | 222 | 324 | 1111 | 35354 | **0.4066** | **0.1665** | **0.2363** | 0.0360 | 0.0695 |
| OLD | realized≠default | 402 | 144 | 6196 | 30269 | 0.7363 | 0.0609 | 0.1125 | 0.1783 | 0.3026 |

Predicted change = `pred != jp_default` (equiv. `pred != jp_ctx` on this stratum).

## 4. Extra cuts

### Among exact_alt positives only (n=1333)

| metric | n | rate |
|---|---|---|
| pred == jp_realized (exact match) | 220 | 0.1650 |
| pred change (≠ default) | 222 | 0.1665 |
| pred change **and** exact match | 220 | 0.1650 |

(So nearly every predicted change on an exact_alt row also hits the correct reading: 220/222.)

### Overrides (pred ≠ jp_ctx), exact_alt-relevant

| metric | n |
|---|---|
| n_pred_ne_ctx | 737 |
| true_win (all) | 474 |
| true_lose (all) | 164 |
| true_win on exact_alt | 346 |
| true_lose on exact_alt | 0 |
| true_win among ctx=default by jp_match | {'tone': 99, 'exact_alt': 220, 'segment': 21} |

## Tom’s “old 6.1% ≈ 30% of reachable” claim

| quantity | value |
|---|---|
| old recall | 0.0609 (6.1%) |
| n_exact_alt in eval ctx=default | 1333 |
| old_TP / n_exact_alt (Tom’s approx) | 402/1333 = **0.3016 (~30%)** |
| true reachable recall (new_TP / n_exact_alt) | 222/1333 = **0.1665 (~16.7%)** |
| old_TP that are exact_alt | 222 |

Arithmetic of Tom’s formula checks out (~30%), but it **overcounts** because 180 of 402 old TPs are unreachable (tone/segment/diff). True reachable recall is **16.7%**.

## Recommendation

**DO NOT CONTINUE** — Reachable change-decision F1=0.2363 (P=0.4066, R=0.1665) on exact_alt base rate 3.6%; always-change F1=0.0695. True reachable recall 16.7% (Tom approx old_TP/n_exact_alt=30.2%). Still directionally positive (win 474>164, EM Δ=+0.0080) but absolute coverage of reachable alts and EM lift remain too small for a product line.

Even under the fairer reachable label, recall covers only ~1/6 of exact_alt rows; precision drops to ~41% (many overrides land on unreachable mismatches). EM Δ remains ~+0.008. Not enough for a product line.
