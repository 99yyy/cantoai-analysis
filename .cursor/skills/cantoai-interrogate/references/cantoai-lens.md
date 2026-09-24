# Project lens: cantoai-analysis

Apply the parts that fit the change. Cite the clause or file for each finding.

## The analysis contract (`.cursor/rules/analysis-contract.mdc`)

For code in `src/` and `tests/`:

- **Clause 7.** Every assertion message in `src/` is unique and has a test that trips it with `pytest.raises(<type>, match=r"^<message>")`. The body of that `pytest.raises` calls a function imported from `src/`, unmocked. An early `return` that guards a data invariant must be a `raise`.
- **Clause 8.** Each defect class whose code path exists in `src/` has a mutation patch in `tests/mutations/` with a `# kills: <message>` header.
- **Clause 9.** Path-bearing names end in `_PATH`, `_DIR`, `_FILE` or `_ROOT` and have no default. No `environ.get(..., default)`, no argparse `default=` for them, no absolute path literals.
- **Clause 10.** A script that writes more than one output, or runs over 60 seconds, writes to a temporary name, renames, and brackets the work with `STATUS.json` (`running`, then `complete` with the output sha256).
- **Clauses 11 and 14.** SQL lives in `.sql` files, never in string literals in `src/`. Every DataFrame join goes through `checked_merge`.
- **Clauses 15 and 17.** No sentinel numbers or `fillna`, `COALESCE`, `or 0` on a measure column. Duplicate columns or keys raise.

Also:

- Code in `src/` may not be imported by the gate tests listed under `gate_tests` in `scripts/gate_config.json`, and nothing may change `scripts/`, `.github/`, `benchmarks/`, `data/` or the agent instruction files.
- A change to a shared `src/` module can move numbers in closed tasks. Ask which tasks call it and whether their routes still replay.
