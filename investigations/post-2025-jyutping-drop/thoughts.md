# thoughts

Scratch from closed findings. Not a scoresheet. No new numbers here.

## Closed

- TASK-6 (`tasks/TASK-6.md`, closed): contract gap ~9.05pp on judgeable A+B. Film title-proxy Kitagawa mix term ~1.91pp; residual ~7.14pp. Rare-character share is lower after 2024, so that mix does not account for the drop as a composition story. Film DID is negative (the film cell drops less than `other`). Auditor Finding 2: the open-analysis sentence that the residual sits in tone and segment disagreements was stronger than the evidence — `rate_tone_*_pm` / `rate_segment_*_pm` are all-A+B per-mille rates, not a partition of the judgeable residual. See `review/TASK-6/audit.md`.
- TASK-7 (`tasks/TASK-7.md`, closed): other×common cell gap ≈7.33pp; cluster bootstrap 95% CI excludes 0; `ci_unreliable=0`. The remaining drop is in that cell, not in film mix or rare characters. See `tasks/TASK-7/RESULT.json` and `review/TASK-7/audit.md`.
- TASK-8 (`tasks/TASK-8.md`, closed): on judgeable A+B, `gap_share_tone_pp` ≈ 3.58 and `gap_share_segment_pp` ≈ 4.02, larger than `gap_share_diff_pp` ≈ 1.45. Finding 2's missing table is now a dual-agreed partition; the labels are still model tags. Share gaps summing to the same size as the contract drop is an identity, not a cause (issue #90). See `tasks/TASK-8/RESULT.json` and `review/TASK-8/audit.md`.

## Next

TASK-9 is open: pin-unchanged proxies on existing columns (`flag_sing`, `coverage`, …), same period and published-set definitions as TASK-8, without redeclaring TASK-8 `jp_match` shares. Brief: `tasks/TASK-9.md`. Do not treat this folder as having measured those proxies.

SNR / singing_prob / content_type stay on `PLAN-corpus-columns.md` until Tom approves a rebuild outside this repo.
