# External published-reference evaluator

Offline, standard-library evaluator for separately supplied FLEURS Cantonese
reference bundles. This directory contains code and synthetic fixture generators
only. No reference selection, row export, audio, source-pin file, prediction,
model weight, or empirical score is distributed.

## Test

From the repository root, run:

```
python -m unittest discover -s investigations/external-reference-evaluator/tests -v
python -m unittest discover -s investigations/external-reference-evaluator/vendor -v
pytest -q tests/test_external_reference_evaluator.py
```

Tests generate invented records and simulated receipts in temporary directories.
No network, dataset download, audio decoding, or inference occurs. The repository
pytest entry point also runs both standalone suites. `synthetic_smoke.py --out`
accepts a new output directory and checks arithmetic on invented text only.

## Local inputs and trust

`adapter.py --help` lists `prepare`, `validate`, `freeze`, and `run`. Each requires
an explicit `--source-pins` file supplied by the operator independently of the
bundle being validated. Missing pins fail closed. Keep this trust anchor outside
the bundle and freeze it before predictions; accepting pins from an untrusted
bundle would authenticate nothing. The code does not establish the provenance
of a caller-selected trust anchor.

The pin document has exactly `reference`, `audio`, and `projection` objects,
with lowercase SHA-256 digests. The required names are defined and validated by
`pinned_source()`. `prepare` checks source-file digests before parsing; validation
checks the bundle lock, source projections, split reservations, and trusted pins.
There is no automatic pin creation or network discovery. Paths are local inputs;
outputs must not already exist. Multi-file outputs begin with `STATUS.json`
marked running, promote temporary files atomically, then mark complete with file
hashes. Bundle readers reject incomplete or hash-mismatched output.

This public packaging variant is version 1.1.0. It requires explicit external
pins instead of loading a bundled pin file. Existing version 1.0.0 bundles and
freeze files must not be silently reused or relabeled: prepare a new local bundle
and perform a new pre-prediction freeze. The vendored scoring engine is unchanged
and its code checksum is checked on import.

## Measurement boundaries

The schema is intentionally limited to 10 development and 20 held-out feasibility
records at the declared upstream revision. These are constraints, not a released
reference selection. Published read-prompt references are not newly listened-to
or manually annotated ground truth. Source-text groups are not speaker identity;
corpus and model-pretraining overlap remain unknown.

Primary CER is aggregate character edit errors divided by reference code points,
with NFC and normalized line endings. Optional punctuation/whitespace-filtered
CER is separate. There is no script, spelling, case, number or English mapping,
no hidden row dropping, and no CER-to-accuracy conversion. Every configured system
must provide exactly one prediction for every reference; an empty prediction is
valid while a missing prediction is rejected.

A test run requires an explicit operator freeze declaration that binds model
specifications, configuration, code, policy and bundle. Local hashes cannot prove
freeze timing or how predictions were produced. Synthetic configurations are
labeled as synthetic and cannot claim empirical model results. Decoder receipts
are checked as metadata; the evaluator does not inspect current audio bytes.
