# Bugbot review focus for cantoai-analysis

This repository is a research-analysis codebase governed by `.cursor/rules/analysis-contract.mdc`. Review every pull request against that contract, and flag the following as blocking, quoting the line.

- A gate function that gains a parameter which can switch it off (`enforce=False`, `strict=False`, `check=False`), or a second code path that performs the same operation without the gate. Example from this repository's history: `left_attach()` added beside `checked_merge()` with "no expected_rows gate".
- A check whose `expected` and `observed` both come from files written in the same pull request by the same author. Name the two files that mirror each other.
- A bar changed in the same pull request as `src/`, `sql/` or `data/`, or a bar changed with no `BAR-CHANGE:` line in the body. A declared expected value, a tolerance, a threshold, a mutation patch and a counterexample pattern are bars; a bar added for new code is not a bar moved.
- An assertion with no counterexample test, or a `pytest.raises` whose body raises itself or calls nothing from `src/`.
- `fillna`, `mask`, `where`, `nan_to_num`, `replace`, `COALESCE`, `errors="coerce"`, `or 0` or `.get(col, default)` on a measure column.
- A sentinel number (0, -1, 999, 9999) written where a NULL and a `_status` column belong.
- A group or stratifier defined as the complement of another (`~df.treatment`, `!= 1`), or built from a column that does not exist in `data/corpus_v2.sqlite`.
- A filter on `dur > 0`, or any denominator that drops zero-width syllables, without the removed count declared in the manifest. Durations are unreliable by construction; onsets are not.
- `review_prior` used to stratify, filter or weight a statistic computed from `jp_match`.
- An agreement figure whose four counts (`n_match`, `n_total`, `n_empty_realized`, `n_dur_le_0`) are not all present in the output.
- A number reported by a run that did not first compare the corpus sha256 against `README.md`.
- Two measurements with different time spans (`t0_s`, `t1_s`) in one row or one comparison.
- Any SQL string literal in `src/` outside the module defining `load_sql`; any absolute path; any `environ.get` with a default.
- A pull request from an agent branch that touches `.cursor/`, `.github/` or `data/`.
- A modified assertion in `tests/` whose matching `src/` assertion is not changed in the same pull request.
- Prose in the pull-request body that asserts correctness ("all checks pass", "verified") without a command whose output is shown.

Do not comment on style, naming or formatting. Do not suggest adding features. One comment per finding, anchored to the line.
