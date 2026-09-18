# Bugbot review focus for cantoai-analysis

This repository is a research-analysis codebase governed by `.cursor/rules/analysis-contract.mdc`. Review every PR against that contract, and flag the following as blocking, quoting the line:

- A gate function that gains a parameter which can switch it off (`enforce=False`, `strict=False`, `check=False`), or a second code path that performs the same operation without the gate. Example from history: `left_attach()` added beside `checked_merge()` with "no expected_rows gate".
- A check whose `expected` and `observed` come from files written in the same PR by the same author (an `expected/` file mirroring `frame.yaml`). Say which two files mirror each other.
- An assertion with no counterexample test, or a `pytest.raises` whose body raises itself or calls nothing from `src/`.
- `fillna`, `mask`, `where`, `nan_to_num`, `replace`, `COALESCE`, `errors="coerce"`, `or 0`, `.get(col, default)` on a measure column.
- A sentinel number (0, -1, 999, 9999) written where a NULL and a `_status` column belong.
- A group or stratifier defined as the complement of another (`~df.treatment`, `!= 1`), or built from a column that does not exist in `fixtures/schema.sqlite`.
- Two measurements with different time spans (`t0_s`, `t1_s`) in one row or one comparison.
- Any SQL string literal in `src/` outside `sql_loader.py`; any absolute path; any `environ.get` with a default.
- A PR that touches `.cursor/`, `.github/`, `fixtures/schema.sqlite`, `fixtures/manifest.schema.json`, `data/`, or `rounds/` from a `cursor/` branch.
- A modified assertion in `tests/` whose matching `src/` assertion is not changed in the same PR.
- Prose in the PR body that asserts correctness ("all checks pass", "verified") without a command whose output is shown.

Do not comment on style, naming, or formatting. Do not suggest adding features. One comment per finding, anchored to the line.
