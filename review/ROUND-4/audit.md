FINDINGS: 5

Range audited: `ed8cefa318b1b2bd3dbdcad589e7671b6ba4870f` (exclusive) .. `b041c9c7f4a6ef86d8bbb97fe7ad295c767b0f5a` (inclusive) on `origin/main`. PR bodies read: #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #25, #27, #28, #29, #30, #31. #24 and #26 were not in the merge list; #26 was read only to confirm it did not merge.

---

## (1) Was any bar moved to make a check pass?

YES. Three declared `expected/` values were rewritten on the same branch after `contract-check` failed, then the PR went green and merged. A mutation patch was also rewritten in the same commit as `src/`.

### 1a. `expected/` rewritten after FAIL on `chore/add-round-4-spec` (PR #14)

Parent `e330a22123c566ed48aa87a7afa3b23d0acd1a16` already had `rounds/ROUND-4.yaml` line 8 `comparisons: []` and line 5 `baseline_model: none`, while the bars still described ROUND-3. GitHub Actions run 35325087061 (`contract-check` on that sha) printed:

```
FAIL comparisons_m
FAIL comparison_ids
FAIL baseline_model
FAIL singing_prob_path_matches_round_yaml
38 checks; FAIL=4 SKIP=0
```

The next commit on the same branch, `15ea35a8fbe96b739a230a1f6aa16bda6909bdc5` (`fix(round-4): align expected/ fixtures with empty comparisons`), moved the bars. The commit message says the move is to make CI pick the empty round. PR #14 body has no `BAR-CHANGE:` line.

| bar | before (`e330a22`) | after (`15ea35a`) |
|---|---|---|
| `expected/comparisons_m.count` line 1 | `3` | `0` |
| `expected/comparison_ids.txt` line 1 | `c1_period_drop,c2_highsnr_onset_residual,c3_singing_removal` | file emptied (zero lines) |
| `expected/baseline_model.txt` line 1 | `agreement_pre2025` | `none` |

The fourth FAIL was cleared in the same commit by adding `rounds/ROUND-4.yaml` lines 26–33 `singing_prob_source.path` (observed round yaml, not an `expected/` bar). After `15ea35a`, run 35325217182 was SUCCESS and #14 merged as `40d92a17c240afd57a2300cc67162a0bef0636d1`.

This is after a failing check on the same branch, not before.

### 1b. Mutation patch rewritten with `src/` (PR #16)

`6a41033116b67269124b545b1ebbf034e6ffc176` (`Fix four contract_check failures on main`) changed `tests/mutations/join_key_swapped.patch` (header still `# kills: checked_merge join keys do not match frame.yaml joins`, hunk context moved from `checked_merge` keys to `right_work.rename`) in the same commit as `src/round3.py` line 43 `MANIFEST_STRATUM_COUNT_NONE` and `tests/test_assertions.py` new `match=` tests. A mutation patch is a bar. Both PR-branch runs on `cursor/contract-green-8511` were SUCCESS; the failures named in the commit message were on `main`, not observed as a red run on that branch.

### Not a bar move

`770e9e88f73e6b950d7255a61acf752efdfc9251` `frame.yaml` lines 118–119 add `joins.video_flags.expected_rows: 567` (new join). `8593062d48bc600419e1daace8e23f9a89729525` adds three mutation patches (new bars). `git log ed8cefa..b041c9c -- scripts/contract_check.py` is empty (check count in that file did not move).

---

## (2) Did any claim assert something no check verifies?

YES. Claims that `contract-check` emits the four new named rows are not verified by any `checks.json` row. The sha256 *value* later has a pytest; `contract_check.py` still never reads the sqlite.

Quote, frozen spec `d50e2dac57f39677fb98367ec600ea51c6600806` `rounds/ROUND-4.md` line 28 (same text at `b041c9c` line 28):

> 若 H1–H3：CI `contract-check` 对下列检查均为 PASS：`merge_pd_merge_once`（或等价名）、`no_boolean_gate_bypass`、`review_no_import_src`、`corpus_sha256_matches_frame`

Quote, same file line 22:

> `contract_check` 对「gate 函数不得有布尔关闭参数」为 PASS。

Quote, PR #29 body (`e565dcbcb95e8d775edf61468b39314accbf661d`): `H1–H3 hold`.

Quote, close-out `262cb633177b26ef61497220a69544c3a0b19762` `rounds/ROUND-4.md` line 80:

> H1–H3 成立；问题答案为**是**（三检查全绿；语料 sha256 与 `frame.yaml: inputs` 一致 …

Check that would have to exist: `scripts/contract_check.py` must `rows.append` four checks named `merge_pd_merge_once`, `no_boolean_gate_bypass`, `review_no_import_src`, `corpus_sha256_matches_frame`, with `expected_source` pointing at `frame.yaml` / `src/merge.py` / `review/` as appropriate, and `corpus_sha256_matches_frame` hashing the file at `frame.yaml: inputs.corpus_path`.

Evidence the check is absent: `719f2129d139d385c36fc1ef4f61c41b66a5a40a` `review/ROUND-4/recompute/numbers.json` lines 7–11 all four names `false`; `b041c9c` `scripts/contract_check.py` has no those identifiers (the checker’s `row(` list at lines 448, 503, 536 is `comparisons_m` / `baseline_model` / `singing_prob_path_matches_round_yaml`, not the four).

`8593062` `tests/test_round4_gates.py` line 248 `test_corpus_sha256_matches_frame` does hash `data/corpus_v2.sqlite`. That is a `tests` job, not a `contract-check` row. `4f4027f183c2391f7c8fbe871207f6fe1fc51a06` `rounds/ROUND-4.md` line 82 then claims 没有任何 CI 检查校验它 — that sentence is false about pytest; the missing check remains the `contract_check.py` row named in the prediction.

`a9eb8ddb4b598a24e6a59d9cee95b858f589d09e` `review/ROUND-4/method.md` line 13 claims 四条新规则可由 `contract_check` 静态重算. That file is not in the question’s source list; the same claim is in ROUND-4.md line 28 and PR #21’s “通过” body.

---

## (3) Write outside declared scope, or merge without required checks green?

YES on scope. NO on merge-head required checks: every merged PR in the list had `tests`, `contract-check`, and `scope-check` SUCCESS on the head that merged. `history-audit` was not a required job until `933b1afc32de302ebea5b9c37dce4e8d689e6a05` (PR #30); #30 and #31 had it SUCCESS. #26 `cursor/r4-impl_b-merge-gate-8823` closed with `tests` FAILURE and did not merge.

### Out of scope (scope-check still SUCCESS because the branch class was skipped)

1. `6a41033116b67269124b545b1ebbf034e6ffc176` on `cursor/contract-green-8511` (PR #16) wrote `src/round3.py` line 43, `sql/count_syllables.sql`, `sql/windows_ab.sql`, `tests/test_assertions.py`, and `tests/mutations/join_key_swapped.patch` together. That is impl plus tests. The name does not match `cursor/r<N>-<scope_id>-`. `a8424ee54b3b0c49e3dd621f2b4790a7970a334a` `scripts/scope_check.py` lines 7–8: branches that do not follow the pattern are not checked (`exit 0`).

2. `15ea35a8fbe96b739a230a1f6aa16bda6909bdc5` on `chore/add-round-4-spec` (PR #14) wrote `expected/comparisons_m.count` line 1, `expected/comparison_ids.txt`, `expected/baseline_model.txt`. `0904853143f1976c8532eda3c960bbebffccc46d` `LAYOUT.md` line 33: `chore/` is not scope-checked. `expected/` is not a later chore allow path.

3. `30dd8f0e349dd019d0b65129ff9eb7a8e486a790` (PR #18) and `a9eb8ddb4b598a24e6a59d9cee95b858f589d09e` (PR #21) on `chore/r4-method-*` wrote `review/ROUND-4/method.md` line 1. `0904853` `LAYOUT.md` line 19 requires `cursor/rN-mr_<mandate>-` and `review/ROUND-N/method/<mandate>.md`. `b041c9c` `rounds/ROUND-4.yaml` lines 11–15 declare `impl_a` / `impl_b` / `tests` / `review` only — no `mr_*` scope.

4. `fb07a627717f5dbaede51029019e3d7c6b5253fb` on `chore/add-corpus-v2` (PR #13) wrote `data/corpus_v2.sqlite` and `frame.yaml` lines 8–10 `inputs`. Those paths are not chore-declaration paths.

In-scope merges: `8593062` / #25 only `tests/`; `770e9e8` / #27 `src/`, `sql/`, `frame.yaml`; `719f212` / #28 `review/ROUND-4/result.md` and `review/ROUND-4/recompute/`.

---

## (4) Was any conclusion stated more strongly than its evidence?

YES. The stage-5 close-out states H1–H3 and a sha256 match as the round answer. There is no ROUND-4 metrics file carrying a count, a p-value, or `ci_unreliable`.

`719f2129d139d385c36fc1ef4f61c41b66a5a40a` `review/ROUND-4/result.md` line 10: `ROUND-4/` 目录不存在. Same commit `review/ROUND-4/recompute/numbers.json` line 2 `"metrics_files": []` and lines 16–18 `n_metrics_json` mine/reported `0`. `b041c9c` `rounds/ROUND-4.yaml` line 9 `comparisons: []`.

Against that empty metrics set, `262cb633177b26ef61497220a69544c3a0b19762` `rounds/ROUND-4.md` line 80 answers 是, including 语料 sha256 与 `frame.yaml: inputs` 一致. Same commit `RESEARCH_LOG.md` line 82: `H1/H2/H3 均成立` and `sha256=2bd618ba… 与 frame 一致；joins 字面量与语料计数一致（4439/567）`. The 4439 sits in `review/ROUND-4/recompute/numbers.json` line 33, not in a metrics JSON; no row has `p`, `p_bh`, `G_h`, or `ci_unreliable`.

No ROUND-4 claim restates a ROUND-3 p-value or `ci_unreliable` flag. The over-strength is treating H3/sha256/4439/567 as a closed round result when the metrics glob is empty and `contract_check` does not hash the corpus.

---

## (5) Was declared task left undone while the round was closed as complete?

YES. The written wave-1 task required four new `contract_check` rules. They were never added. The round was closed as complete anyway.

Declared: `262cb63` `rounds/ROUND-4.md` line 49 (`contract_check` 新增四条: `pd.merge(` once; no boolean gate; `review/` must not `import src`; corpus sha256 equals `frame.yaml: inputs`). Same file line 18 is the falsifiable question, which includes those four rules. Close-out at line 80 问题答案为是; line 83 records the missing names as advisory 不计入打回. `git log ed8cefa..b041c9c -- scripts/contract_check.py` prints nothing.

Done in the merged diffs: `770e9e88f73e6b950d7255a61acf752efdfc9251` `src/merge.py` line 25 has no `enforce_expected` parameter; line 55 always compares `matched != expected_rows`; `left_attach` at line 80 calls `checked_merge`. `8593062` adds `tests/test_round4_gates.py` and three mutation patches. No `ROUND-4/<comparison_id>/` tree, matching `comparisons: []`.

`rounds/ROUND-4.yaml` write_scopes (from `1eb2dddd42328e476db80b13e2ca29d9faaac246` through `b041c9c` lines 12–15) never include `scripts/`. The launched impl/tests agents could not add the four `contract_check` rows; no `repair/` or other merged commit in the range added them either before close.

---

## (6) Which findings can become a mechanical check?

Propose only conditions. Do not treat the current `expected/comparisons_m.count` value `0` as a wrong bar to edit; it matches `rounds/ROUND-4.yaml` line 9. The defect is the rewrite after FAIL, not the empty-round literal.

1. Finding 1a (expected/ rewrite, no `BAR-CHANGE:`). File: `scripts/history_audit.py` (already at `2905d9064ff9f1b5ddc189136a1e5ff560c2f41d` lines 146–150). Condition already stated there: if a path matching `expected/*` existed on base and changed, FAIL unless the PR body has a line starting `BAR-CHANGE:`. That condition would have failed PR #14. No new bar.

2. Finding 1b (existing mutation patch content changed with `src/`). File: `scripts/history_audit.py`. Condition: if `tests/mutations/*.patch` exists on base and `git hash-object` of that path differs at HEAD, treat it as a bar; then the existing rule at lines 141–144 FAIL when any `src/**` path also changed in the same PR. Adding patches remains unflagged (`len(h_pat) < len(b_pat)` already covers only net removal).

3. Findings 2 and 5 (named `contract_check` rows claimed but absent). File: `scripts/contract_check.py`. Condition: after the round markdown is read, for each of the identifiers `merge_pd_merge_once`, `no_boolean_gate_bypass`, `review_no_import_src`, `corpus_sha256_matches_frame` that occurs in `rounds/ROUND-N.md`, append a `checks.json` row with that `name`; status FAIL if the name is not produced by this script’s own `row(` / `compare_check(` calls. Separately, always append `corpus_sha256_matches_frame` with `expected_source` `frame.yaml:inputs.corpus_sha256`, `expected` equal to that yaml value, `observed` equal to sha256 of the bytes at `frame.yaml:inputs.corpus_path`, FAIL if unequal or if the path is missing (`missing` set, SKIP). Always append `merge_pd_merge_once` with expected `1` and observed the count of the token `pd.merge(` in `src/merge.py`. Always append `no_boolean_gate_bypass` FAIL if `src/merge.py` function `checked_merge` or `left_attach` has a parameter named `enforce_expected` (or another name in the set already used by `tests/test_round4_gates.py` `GATE_PARAM_NAMES`). Always append `review_no_import_src` FAIL if any file under `review/` matches `(?m)^\s*(import src\b|from src\b)`.

4. Finding 3 (unscoped / chore writing `expected/` or `review/`). File: `scripts/scope_check.py` (already at `6ef08587a2d25b58b8ad86f3cb9ccfd997cd010f`). Conditions already stated: branch must match `cursor|box/r<N>-<scope>-`, `chore/`, or `repair/`; anything else FAIL; `chore/` may change only `CHORE_ALLOW` (no `expected/`, no `review/`, no `src/`, no `tests/`, no `data/`). Those conditions would have failed #16, #14, #18, #21, #13.

5. Finding 4 (close-out stronger than empty metrics). File: `scripts/contract_check.py`. Condition: if `rounds/ROUND-N.yaml: comparisons` is `[]` and `glob('ROUND-N/*/metrics/*.json')` is empty, FAIL if `rounds/ROUND-N.md` or `RESEARCH_LOG.md` contains the substring `H1–H3 成立` or `H1/H2/H3 均成立`. That is the exact over-strength string this round used; it does not require parsing p-values from absent files.

6. Finding 5 extra (tests that pass while the defect is still in `src/`). File: `scripts/contract_check.py`. Condition: FAIL if any `tests/*.py` contains the line fragment `if "enforce_expected" in params:` (see `8593062` `tests/test_round4_gates.py` lines 204 and 222). The adversary tests must not special-case the bypass they claim to kill.

No other finding in (1)–(5) has a condition that can be stated without reading GitHub Actions logs from outside the tree.
