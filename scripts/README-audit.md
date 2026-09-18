# `scripts/audit.py`

Read-only process audit. Spec: `docs/AUDIT-SPEC.md`. Stdlib + `sqlite3` only; does not mutate the corpus or analysis CSVs.

Checks: **C1–C9, C13, L1–L6, T1, T3, T4**. With `--round 2` also **R1–R5**.

Each line: `PASS|FAIL|SKIP <id> <measured> (expected: …)`. Exit `1` if any FAIL.

Known 2026-09-18 corpus failures (C3–C6, C8, C9, C13, L1–L6, T1, R1–R3) must still FAIL on the real DB. Expected values are not relaxed to match reality.

## Self-test (no full corpus)

```bash
python scripts/audit.py --self-test
```

## Smoke on committed fixtures

```bash
ICANTO_ROOT=fixtures/audit/icanto \
ANALYSIS_ROOT=fixtures/audit/analysis \
python scripts/audit.py --round 2
```

This mixed fixture is *meant* to FAIL the same classes of checks as the Sep-18 corpus (subscribe boiler, nested `dataset_v2/`, empty `jp_realized`, etc.). It should print a one-screen summary and exit non-zero without crashing.

Regenerate the tree:

```bash
python scripts/audit.py --write-fixtures
```

## Real corpus (read-only)

Paths come from the environment; nothing is hardcoded.

```bash
export ICANTO_ROOT=/workspace/cantoai          # corpus root
export ANALYSIS_ROOT=.                         # this repo
python scripts/audit.py                        # C / L / T only
python scripts/audit.py --round 2              # plus listening-sheet R1–R5
```

`ICANTO_ROOT` should contain `corpus/dataset_v2` (or equivalent), `corpus.sqlite`, pipeline scripts (`common.tier_of`, `09_*`, `10_validate`, `12_review_sample`), `STATS.json`, `ids.txt`, and per-video `info.json`. `ANALYSIS_ROOT` should contain `ROUND-2/listening_sheet.csv` and `rounds/ROUND-2.md`.
