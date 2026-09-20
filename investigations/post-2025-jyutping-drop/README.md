# post-2025-jyutping-drop

This folder is the **index of record** for the campaign. Machine-gated numbers and `RESULT` live under `tasks/` and `review/`, not only here.

**Question.** On the 567 videos of this channel, why does published (tier A+B) Jyutping agreement fall after 2024?

## Status

| Item | Status | Finding (one line) | Where |
|---|---|---|---|
| TASK-6 | closed | Film title-proxy mix term ≈ 1.91pp of `gap_contract_pp` ≈ 9.05pp; residual ≈ 7.14pp. | [brief](../../tasks/TASK-6.md) · [results](../../tasks/TASK-6/results.json) · [audit](../../review/TASK-6/audit.md) · [PR #46](https://github.com/99yyy/cantoai-analysis/pull/46) |
| TASK-7 | closed | other×common `gap_other_common_pp` ≈ 7.33pp; cluster 95% CI excludes 0. | [brief](../../tasks/TASK-7.md) · [RESULT](../../tasks/TASK-7/RESULT.json) · [audit](../../review/TASK-7/audit.md) · [PR #83](https://github.com/99yyy/cantoai-analysis/pull/83) |
| TASK-8 | closed | On judgeable A+B, tone and segment share gaps (≈ 3.58 and ≈ 4.02 pp) larger than diff (≈ 1.45 pp). | [brief](../../tasks/TASK-8.md) · [RESULT](../../tasks/TASK-8/RESULT.json) · [audit](../../review/TASK-8/audit.md) · [PR #87](https://github.com/99yyy/cantoai-analysis/pull/87) |
| TASK-9 | **open** | Pin-unchanged diagnostic: existing-column proxies (`flag_sing`, `coverage`, …) pre vs post; Q2 cluster-median + trim10 of the same gaps (19 names). No results yet. | [brief](../../tasks/TASK-9.md) |
| Corpus columns | deferred | SNR / `singing_prob` / `content_type` need a pipeline rebuild outside this repo. Not executed here. | [PLAN](PLAN-corpus-columns.md) |

Quotes of closed findings are pointers to `tasks/` / `review/`. This folder does not re-judge them and does not invent new numbers.

## Index of related paths

Campaign notes (this tree):

- [`README.md`](README.md) — this index
- [`thoughts.md`](thoughts.md) — short scratch; closed findings only
- [`PLAN-corpus-columns.md`](PLAN-corpus-columns.md) — Tom checklist for a future corpus rebuild (doc only)
- [`scripts/.gitkeep`](scripts/.gitkeep) — placeholder for exploratory scripts (not gated)
- [`artifacts/.gitkeep`](artifacts/.gitkeep) — placeholder for local artifacts (not gated)
- Parent: [`investigations/README.md`](../README.md)

Tasks and review:

| Path | What |
|---|---|
| `tasks/TASK-6.md` | Brief (closed) |
| `tasks/TASK-6/` | `sql/`, `mine_sql/`, `results.json`, `mine.json`, open analysis |
| `review/TASK-6/audit.md` | Auditor |
| `tasks/TASK-7.md` | Brief (closed) |
| `tasks/TASK-7/` | outputs + `RESULT.json` |
| `review/TASK-7/audit.md` | Auditor |
| `tasks/TASK-8.md` | Brief (closed) |
| `tasks/TASK-8/` | outputs + `RESULT.json` |
| `review/TASK-8/audit.md` | Auditor |
| `tasks/TASK-9.md` | Brief (open); no `tasks/TASK-9/` outputs yet |

Issues and loop docs:

- [Issue #89 质询清单与工作规程](https://github.com/99yyy/cantoai-analysis/issues/89)
- [Issue #90 TASK-8 Q3 旧账](https://github.com/99yyy/cantoai-analysis/issues/90)
- [`LOOP.md`](../../LOOP.md) — execution playbook
- [`BACKGROUND.md`](../../BACKGROUND.md) — columns and wording
- [`backlog.md`](../../backlog.md) — keep rates; not a second scoresheet

PRs (campaign so far):

- Convention: [#80](https://github.com/99yyy/cantoai-analysis/pull/80)
- TASK-6: [#44](https://github.com/99yyy/cantoai-analysis/pull/44) verifier, [#45](https://github.com/99yyy/cantoai-analysis/pull/45) worker, [#46](https://github.com/99yyy/cantoai-analysis/pull/46) close
- TASK-7: [#77](https://github.com/99yyy/cantoai-analysis/pull/77) brief, [#78](https://github.com/99yyy/cantoai-analysis/pull/78) verifier, [#79](https://github.com/99yyy/cantoai-analysis/pull/79) worker, [#83](https://github.com/99yyy/cantoai-analysis/pull/83) close
- TASK-8: [#84](https://github.com/99yyy/cantoai-analysis/pull/84) brief, [#85](https://github.com/99yyy/cantoai-analysis/pull/85) verifier, [#86](https://github.com/99yyy/cantoai-analysis/pull/86) worker, [#87](https://github.com/99yyy/cantoai-analysis/pull/87) close

## Next

TASK-9 (open, Autopilot). Worker / verifier start from the same ref after this brief lands. Corpus rebuild stays on the PLAN until Tom approves it; this analysis repo will not download audio or models.
