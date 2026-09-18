# Audit fixtures

Mixed mini-corpus for `scripts/audit.py` smoke. It is **supposed** to FAIL
the same classes of checks as the 2026-09-18 corpus. Expected values stay
at the spec (e.g. `== 0`); they are not relaxed to match measured counts.

```bash
ICANTO_ROOT=fixtures/audit/icanto \
ANALYSIS_ROOT=fixtures/audit/analysis \
python scripts/audit.py --round 2
```

`python scripts/audit.py --self-test` is the green bar.
