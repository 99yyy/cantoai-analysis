---
name: cantoai-tdd
description: "Use when fixing a bug in src/ or tests/ of this repository and a cheap local test can show it: write a test that fails first, confirm why it fails, then make the smallest fix. Skip for SQL routes and task output files, and when the test path is unclear, expensive or integration-heavy."
paths:
  - "src/**"
  - "tests/**"
---

# cantoai-tdd

Adapted from the `tdd` skill of pstack 0.15.5 (`cursor/plugins`, MIT, see `../LICENSE-pstack`). A section for this repository is added at the end.

When fixing a bug with a clear, cheap test path, make the broken behavior executable before changing production code. The goal is a focused regression test that fails before the fix and passes after it.

Do not force a test when it would be impractical. If the test would need broad harness setup, brittle mocks, slow end-to-end infrastructure, production-only state, vague reproduction steps or large unrelated fixture churn, skip the new test and use the closest useful check instead.

## Workflow

1. **Understand the bug.** Identify the intended behavior, the current behavior, the affected path and the smallest observable reproduction.
2. **Choose the narrowest executable check.** Prefer the closest unit or regression test already used for that code path. If no practical test path is obvious, do not create one from scratch just to satisfy the workflow.
3. **Write the failing test first.** Add the smallest focused test that would have caught the bug. It encodes intended behavior, not the current implementation.
4. **Run it before fixing.** Confirm it fails for the intended reason. If it passes, or fails for an unrelated reason, fix the test or the reproduction before touching the implementation.
5. **Fix the bug.** Make the smallest production change that gives the intended behavior and keeps nearby contracts.
6. **Rerun the regression test.** Confirm it passes.

## If a failing test is impractical

Use the closest executable check instead: a targeted script, a reproduction command, a snapshot comparison or a log assertion. Prefer no new test over a bad test: one that mostly tests mocks, encodes implementation details, depends on timing or global state, or would be deleted right after proving the fix.

## Guardrails

- Do not change tests to match a wrong implementation.
- Do not modify an assertion that already exists, except in the pull request that changes the code it guards; list each such pair in the pull-request body (analysis contract). Never weaken or delete an existing test to make a fix pass.
- Keep the regression test focused on the bug; add sibling coverage only after the focused test lands.
- If the bug is flaky, make the test deterministic where possible and name the signal it locks down.

## In this repository

- Put a new test in `tests/test_<module>.py` for the module you changed. If that name is a gate file (next item), pick another.
- Gate files are listed in full by `BAR_FILES` in `scripts/history_audit.py` and `gate_tests` in `scripts/gate_config.json`. In `tests/` they include every `tests/test_assertions*.py` and `tests/test_mutations*.py`, the tests of the gate scripts, `tests/fixtures/`, `tests/mutations/`, any `conftest.py` and `tests/__init__.py`; the pytest configuration and `requirements*.txt` are gate files too. A pull request that changes one fails history-audit until Tom adds a `Gate-review:` line after a fresh review. Do not change them unless your launch prompt says so.
- A new assertion in `src/` needs its test, `pytest.raises(<type>, match=r"^<message>")`, whose body calls the function imported from `src/`, unmocked (analysis contract, clause 7). It goes in that module's test file, not in `tests/test_assertions.py`.
- New code of a defect class that clause 8 lists needs a mutation patch in `tests/mutations/`. Adding one for new code is not moving a bar, but the patch is a new gate file: say in your final message that the pull request needs a `Gate-review:` line.
- Changing or deleting an existing gate file, or removing a `match=` pattern from any test, moves a bar. That may not share a pull request with a change to `src/` or any `.sql` file (clause 6). Stop and report it instead.
- A test you add or change also follows the `cantoai-test-behavior` skill.
- Run the focused test with `python -m pytest -q tests/<file>.py`, then `./verify` before you open the pull request.

## Final response

Report the evidence, not only the outcome:

- the failing-before test or check, and the failure it produced;
- the passing-after run and any nearby validation;
- if failing-before evidence could not be shown, why, and which check you used instead.
