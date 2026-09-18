FINDINGS: 4

Range audited: every commit after `854911e54c8d480b205d72056572ff35fb80186d` through `433808e749f35fb55a11b44d68b7a3d0db9014c7` (origin/main HEAD). Pull requests merged in that range: #44 verifier, #45 worker, #46 close. output-check on #46 printed `TASK-6 [closed]: 39/39 number(s) agree`. This file does not re-judge those 39 values.

Findings, numbered once and cited from the questions below:

1. Worker wrote `pytest.ini` outside the declared write scope.
2. The open-analysis conclusion locates the residual in tone and segment disagreements; no check verifies that attribution, and the recorded rates do not isolate it.
3. `manifest.json` omits the six contract-24 counts for the four film/other agreement rates the brief said to record there.
4. Worker `src/` contains a SQL string literal (`select * from`), which clause 11 forbids.

---

## (1) Was any bar moved to make a check pass?

Verdict: no bar was moved.

A bar here is a declared expected value, a tolerance, a threshold, a mutation patch, a counterexample pattern, or a check script.

- Check scripts and CI were not touched. `git diff --name-only 854911e54c8d480b205d72056572ff35fb80186d 433808e749f35fb55a11b44d68b7a3d0db9014c7 -- scripts .github expected` is empty. Unchanged check at `854911e54c8d480b205d72056572ff35fb80186d` `scripts/output_check.py` line 1 (`"""Every number is replayed from the corpus...`).
- The only edit to the brief is status. `29d8d7242839f022340fce33d5c5a673f668f95c` `tasks/TASK-6.md` line 3: `status: open` → `status: closed`. No name, tolerance, or numbers-block line changed. No `BAR-CHANGE:` line appears in #44, #45, or #46 (none was required).
- Mutation patches and `match=` patterns were added with new `src/`, not altered afterwards. First appearance: `856fbd9508a4d59bdb58698240a33cf1872e25e6` `tests/mutations/tier_filter_removed.patch` line 1 (`# kills: published A+B syllable count is outside the declared interval`). Adding a bar for new code is not moving one.
- No required check on #44, #45, or #46 concluded failure. There is therefore no bar change after a failing check on the same branch.

`pytest.ini` was added in `856fbd9508a4d59bdb58698240a33cf1872e25e6` at line 1 (`[pytest]`). That is a write-scope issue (question 3), not a moved bar: the file did not exist at `854911e`, so nothing was lowered.

---

## (2) Did any claim assert something no check verifies?

Verdict: yes. Three claims in the worker write-up and the brief's `n` table have no check; `backlog.md` has no TASK-6 claim.

LOOP.md lines 81–83 say the open-analysis residual is judged by Tom and the auditor, not by output-check. Those residual figures are listed first so they are not confused with defects.

**By design (not a finding):** `1ebd461155e6964d99ec0c8b52822d141b5ae2e5` `tasks/TASK-6/open_analysis.md` line 55, `Residual 95% percentile CI: [4.5998, 9.6243] pp.`, and line 56, `p_raw=0, p_BH=0, m=1.` No declared `numbers` name is replayed for the residual, the interval, or those p-values. The check that would have to exist is an output-check route for those names. LOOP.md line 83 says putting that into a gate produces a false green; do not add it.

**Finding 2 (also question 4):** `1ebd461155e6964d99ec0c8b52822d141b5ae2e5` `tasks/TASK-6/open_analysis.md` lines 75–76, `and sits in tone and segment disagreements rather than in rare-character share.` output-check replays `rate_tone_*_pm` and `rate_segment_*_pm` as all-A+B per-mille rates. It does not replay a residual (or contract-gap) partition by `jp_match` on the judgeable set. The check that would have to exist: a committed table of judgeable pre/post (or residual) mass for `tone`, `segment`, `diff`, and `none`, plus a gate that the conclusion may name a verdict only when that table contains it.

**Brief `n` table, no agent defect:** `854911e54c8d480b205d72056572ff35fb80186d` `tasks/TASK-6.md` lines 115–121 declare what `n` must be (567 for video counts, `n_total_*` for period syllable families, four-cell `n_judgeable_*` for `agree_*`, and so on). `scripts/output_check.py` (same commit, lines 531–535) compares worker `n` to verifier `n` and does not compare either to that table. The check that would have to exist: for each declared name, the written `n` equals the brief table (constants, or an arithmetic expression over other declared names). Both files used the same `n` values, so this gap did not hide a disagreement.

**PR bodies (not in the git tree; retrieved with `gh pr view`):** #45 (merge `7e6ffea5f657098e4c54f95f1ca00470af241d4b`) states `Does not fetch, read, or reason about a verifier branch, pull request, or mine.json.` output-check independence (introducing-commit tree) does not prove a mid-run fetch. LOOP.md lines 77–79 already say CI cannot prove that. Git parents show an independent start (question 3); whether the worker process fetched #44 is UNKNOWN (no agent transcript in this range).

#44 (`56fca2d2e7b8dcbaa2e6c04fef638d8d0957aae7`) `None: every declared number was computed.` is the replay of `mine.json`, which that PR's output-check ran. #46 (`433808e749f35fb55a11b44d68b7a3d0db9014c7`) `output-check reported 39/39 agree` is the close job log.

`backlog.md` at `433808e749f35fb55a11b44d68b7a3d0db9014c7` line 9 still describes ROUND-2 listening-sheet work. It contains no TASK-6 sentence.

---

## (3) Write scope, or a merge without required checks green?

Verdict: finding 1 (and finding 4). Verifier and close stayed inside their scopes. All three merges had `scope-check`, `history-audit`, `output-check`, and `tests` green. Starting refs were independent.

Declared scopes: worker `results.json` + `sql/` + `src/` + `tests/` + open analysis; verifier `mine.json` + `mine_sql/` only; close the status line only.

**Finding 1.** `856fbd9508a4d59bdb58698240a33cf1872e25e6` adds `pytest.ini` line 1 `[pytest]` and line 2 `pythonpath = .` at the repository root. That path is not under `tasks/TASK-6/`, `src/`, or `tests/`. `scripts/scope_check.py` at `854911e54c8d480b205d72056572ff35fb80186d` lines 23–24 (`Per-scope path lists are not checked here.`) is why #45 still passed scope-check. The file was in the first worker commit, together with `tests/`; it was not added after a red tests job.

Open-analysis companions `STATUS.json`, `decomposition.json`, `manifest.json`, and `open_analysis.md` first appear in `1ebd461155e6964d99ec0c8b52822d141b5ae2e5`. They are the decomposition the brief asked for, not a scope breach.

**Finding 4.** `856fbd9508a4d59bdb58698240a33cf1872e25e6` `src/tables.py` line 21: `cursor = conn.execute("select * from " + ident)`. Clause 11 forbids SQL as a string literal in `src/`. The mechanical wording looks for uppercase `SELECT` and `FROM` in one literal, so this line does not trip a current check.

**Verifier.** `ef589e4ac1276091822cf398bf993b53fe74b7da` adds only `tasks/TASK-6/mine.json` and `tasks/TASK-6/mine_sql/*`. Parent is `854911e54c8d480b205d72056572ff35fb80186d`. Worker SQL uses `LIKE` markers (`856fbd9508a4d59bdb58698240a33cf1872e25e6` `tasks/TASK-6/sql/agree_film_pre.sql` line 11); verifier SQL uses `WITH token` / `instr` (`ef589e4ac1276091822cf398bf993b53fe74b7da` `tasks/TASK-6/mine_sql/agree_film_pre.sql` line 1). The implementations are not the same file and not the same text.

**Close.** `29d8d7242839f022340fce33d5c5a673f668f95c` `tasks/TASK-6.md` line 3 only.

**Independence of starting trees.** Worker code commit `856fbd9508a4d59bdb58698240a33cf1872e25e6` parent `854911e`. Results commit `1ebd461155e6964d99ec0c8b52822d141b5ae2e5` parent `856fbd9`; that tree has no `tasks/TASK-6/mine.json`. Verifier commit `ef589e4` parent `854911e`; that tree has no `tasks/TASK-6/results.json`. `results.json` is not rewritten after `1ebd461` (later `0c2ceb416355c4cf8f4d4b4f83a795c2bab7dd03` is a merge of origin/main into the worker branch so the PR could update). Mid-run fetch of #44 is UNKNOWN: no transcript is in git.

**Merges and checks.** Required jobs are `.github/workflows/ci.yml` at `854911e54c8d480b205d72056572ff35fb80186d` lines 10 (`tests:`), 26 (`output-check:`), 45 (`scope-check:`), 61 (`history-audit:`). GitHub check-runs on the merged heads:

- #44 `ef589e4ac1276091822cf398bf993b53fe74b7da`: all four success.
- #45 `1a8ceceeedd742f236994e28dc59d048edc0291e`: all four success (also on `1ebd461` and `75f8499`).
- #46 `29d8d7242839f022340fce33d5c5a673f668f95c`: all four success.

No required check was red at merge.

---

## (4) Was any conclusion stronger than its evidence?

Verdict: yes. Finding 2. The residual size is in line with the interval and flags; the mechanism sentence is not.

Compare `1ebd461155e6964d99ec0c8b52822d141b5ae2e5` `tasks/TASK-6/open_analysis.md` lines 73–76 with the files that commit wrote:

- Unadjusted gap 9.0493 pp, composition 1.9143 pp, residual 7.1351 pp (`tasks/TASK-6/decomposition.json` lines 16–20, 23–25). 1.9143 is a minority of 9.0493. That clause is in line with the point estimates.
- Residual 95% percentile CI [4.5998, 9.6243] pp (`open_analysis.md` line 55; `decomposition.json` lines 75–78). The interval sits above 0. `ci_unreliable_any` is 0 (`decomposition.json` line 73). `conclusion` is `estimated` (line 74). `G_h` is 59, 60, 332, 116 (`open_analysis.md` lines 50–53), all ≥ 10. `other_pre` reports 330 videos with judgeable syllables out of G_h=332, so the two empty-judgeable videos are visible. Saying the residual remains after reweighting matches this block. `p_raw=0` / `p_BH=0` / `m=1` (line 56) are not used in the conclusion sentence.
- Rare-character share pre 0.034499, post 0.031870 (`open_analysis.md` line 37; `decomposition.json` lines 110–111). The share falls. A shift toward rare characters does not describe these two numbers.
- Year cells 2021 n=9 and 2023 n=36 are listed with the warning not to read them as a trend (`open_analysis.md` line 59). That matches the brief.

The over-strong clause is `sits in tone and segment disagreements` (`open_analysis.md` lines 75–76). Evidence actually present:

- `rate_tone_pre_pm` 73.039 → `rate_tone_post_pm` 106.532 (`tasks/TASK-6/results.json` lines 189–197).
- `rate_segment_pre_pm` 46.732 → `rate_segment_post_pm` 86.077 (lines 201–209).
- `rate_diff_pre_pm` 8.076 → `rate_diff_post_pm` 23.820 (lines 213–221).
- `rate_none_pre_pm` 9.312 → `rate_none_post_pm` 24.597 (lines 225–233).

Those four rates are all-A+B per-mille, not a partition of the judgeable residual. `diff` and `none` also rise. `decomposition.json` has no per-`jp_match` residual share. The hypothesis at `open_analysis.md` lines 63–69 is written as data / comparison / result-that-would-refute; that comparison is not run. The conclusion then states the hypothesized mechanism as the finding.

Film DID is −0.9830 pp (`open_analysis.md` line 29; `did_film_pp` in `results.json`). The film title-proxy gap is smaller than the `other` gap; composition still explains 1.9143 pp because post has a higher film share of judgeable syllables. The conclusion does not treat the raw film gap as the story. Population is `the 567 videos of this channel` (`open_analysis.md` line 3 and line 73). The word is agreement.

---

## (5) Was anything in the brief left undone while status was set to closed?

Verdict: finding 3. The 39 names, the two SQL directories, the open-analysis trio (decomposition, hypothesis form, one-sentence conclusion), and the status line are in the merged diffs. The six contract-24 counts per reported agreement rate are not fully in `manifest.json`.

Brief at `854911e54c8d480b205d72056572ff35fb80186d` `tasks/TASK-6.md` line 22: every reported agreement rate must carry `n_total`, `n_match`, `n_judgeable`, `n_empty_realized`, `n_dur_le_0`, and the overlap of the last two, written into `manifest.json`; the pre/post totals and the four `n_judgeable` cells are also in the `numbers` block.

`1ebd461155e6964d99ec0c8b52822d141b5ae2e5` `tasks/TASK-6/manifest.json` lines 169–186 `agreement_counts` has those six keys for `pre` and `post` only. The four cells sit under `stratum_sizes` (lines 187–216) with `n_h_judgeable` and `n_h_match` and without `n_total`, `n_empty_realized`, `n_dur_le_0`, or `n_empty_and_zerodur`. The four `n_judgeable_film_*` / `n_judgeable_other_*` names are in `results.json` and `mine.json`, so output-check nails those denominators and not the other four counts per cell.

Closed at `29d8d7242839f022340fce33d5c5a673f668f95c` `tasks/TASK-6.md` line 3 while that manifest shape was already on main.

Landed, for the rest of the brief:

- 39 names in `results.json` (`1ebd461`) and `mine.json` (`ef589e4`); worker `n_judgeable_*` is `derived:` of the identity (`1ebd461` `tasks/TASK-6/results.json` line 90); verifier counts the judgeable set (`ef589e4` `tasks/TASK-6/mine.json` line 90 query `tasks/TASK-6/mine_sql/count_judgeable_pre.sql`).
- Decomposition, variables, title-proxy wording, residual cluster bootstrap B=2000, year cells: `1ebd461` `open_analysis.md` / `decomposition.json`.
- Hypothesis in the required form: `1ebd461` `open_analysis.md` lines 63–69.
- One-sentence conclusion: lines 73–76 (over-strong; question 4).
- Worker `sql/` + `src/` + `tests/`; verifier `mine_sql/` only; close status only.

LOOP.md keep-rate row in `backlog.md` is not a TASK-6.md requirement; `backlog.md` was not edited in this range. The brief never declared a sampling-frame expected count and tolerance (contract 12); the worker instead put literals in `856fbd9508a4d59bdb58698240a33cf1872e25e6` `src/frame.py` lines 12–15 (`VIDEOS_N = 567` … `PUBLISHED_N = 164693`). That is a missing declaration in the brief, not an item the agents were told to deliver and then skipped.

---

## (6) Which of the findings can be turned into a mechanical check?

Propose only conditions. Do not move a bar in this pull request.

**Finding 1 — per-scope path lists.** File: `scripts/scope_check.py`. Condition: if the branch matches `^(?:cursor|box)/t(\d+)-worker-` then every path in `git diff --name-only {base}...HEAD` must match one of `tasks/TASK-{N}/results.json`, `tasks/TASK-{N}/sql/**`, `tasks/TASK-{N}/open_analysis.md`, `tasks/TASK-{N}/decomposition.json`, `tasks/TASK-{N}/manifest.json`, `tasks/TASK-{N}/STATUS.json`, `src/**`, `tests/**`; otherwise FAIL. If the branch matches `^(?:cursor|box)/t(\d+)-verifier-` then every path must match `tasks/TASK-{N}/mine.json` or `tasks/TASK-{N}/mine_sql/**`; otherwise FAIL. If the branch matches `^chore/t(\d+)-close-` then the only allowed path is `tasks/TASK-{N}.md` and the diff of that file may change only a line matching `^status:[ \t]*(open|closed)[ \t]*$`; otherwise FAIL. This would have failed #45 on `pytest.ini`.

**Finding 2 — conclusion names a `jp_match` value.** File: `scripts/output_check.py` (or a sibling that reads open analysis, not the 39 numbers). Condition: if `tasks/TASK-N/open_analysis.md` contains a `## Conclusion` section, and that section matches `\b(tone|segment|diff|none)\b`, then `tasks/TASK-N/decomposition.json` must contain a JSON object `jp_match_contrib` whose keys include every such word and whose values are numbers; otherwise FAIL. This does not judge whether the prose is true; it refuses a mechanism sentence with no table. Do not add the residual CI to the `numbers` block (LOOP.md line 83).

**Finding 3 — six counts per agreement cell.** File: `scripts/output_check.py`. Condition: if `tasks/TASK-6/manifest.json` exists, then `.agreement_counts` must have keys `pre`, `post`, `film_pre`, `film_post`, `other_pre`, `other_post`, and each value must have exactly the keys `n_total`, `n_match`, `n_judgeable`, `n_empty_realized`, `n_dur_le_0`, `n_empty_and_zerodur`; otherwise FAIL.

**Finding 4 — SQL literals in `src/`.** File: `scripts/output_check.py` or the tests job. Condition: for each `src/**/*.py`, if a string literal matches both `(?i)\bSELECT\b` and `(?i)\bFROM\b`, FAIL and print the path. This would have failed `src/tables.py` line 21. Do not weaken the existing uppercase form; extend it.

**Not a finding this round, still a condition.** File: `scripts/output_check.py`. Condition: parse the `n` column of `tasks/TASK-N.md` (question 2) and require each output row's `n` to equal that declaration (literal 567, or `derived:` over other names such as `n_total_pre + n_total_post`). Pairwise equality of worker `n` and verifier `n` remains.

**Not a finding this round.** File: `scripts/history_audit.py`. Condition: if a tolerance in a `tasks/TASK-*.md` fenced `numbers` block changes value, that path is a bar (same rules as other bars: no co-change with `src/` or `*.sql`, and a `BAR-CHANGE:` line). No tolerance moved here.

**Already true, keep.** File: `src/status_io.py` `read_completed_output`. Condition: if `tasks/TASK-6/STATUS.json` exists, `status` must be `complete` and each `outputs` sha256 must equal the file bytes. Hashes at `1ebd461155e6964d99ec0c8b52822d141b5ae2e5` `tasks/TASK-6/STATUS.json` lines 2–7 still match the three files.

No bar in this range looks wrong. No bar is moved here.
