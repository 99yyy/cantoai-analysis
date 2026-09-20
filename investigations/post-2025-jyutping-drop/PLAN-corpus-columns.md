# PLAN: future corpus columns (doc only)

This is a checklist for Tom. **Do not execute it in this repository.** Do not rebuild the corpus, do not touch `data/`, do not download audio or models, do not add a second copy of `data/corpus_v2.sqlite`.

The measurement loop here only reads the pinned file in `README.md`. New acoustic or content labels require the **pipeline repo**, then a `repair/` PR that updates the sqlite file, the README sha256, and every live `corpus_sha:` stamp together (`LOOP.md` 语料更换).

## Why these columns

TASK-9 can only use columns that already exist (`flag_sing`, `coverage`, `chars_per_sec`, `boundary_*`, `n_windows`, `speech_s`, window `dur`, …). Those are weak proxies and several are model outputs (contract clause 27). They are not SNR, not a singing probability, and not a content type. If the campaign later needs those quantities, they have to be written at corpus-build time.

## Add (pipeline, after approval)

- `snr` (or equivalent) per window, with a documented estimator and a `_status` companion if the analysis contract applies to the writer (`c` non-NULL iff `c_status == "ok"`; no sentinel 0 / -1 standing in for missing).
- `singing_prob` per window from a pinned singing/music detector, not a re-use of `flag_sing`.
- `content_type` per video or window from an explicit label set (not the complement of another class; unassigned counted). Title-keyword film/other stays a title proxy if it remains.

Do not invent these columns inside `cantoai-analysis`.

## Pin models (write into `runs` on rebuild)

Record at least:

| Field | Role |
|---|---|
| `asr_model` | ASR pin |
| `aligner_model` | forced aligner pin |
| `jyutping_model` | acoustic Jyutping pin |
| `tojyutping_version` | dictionary / g2p pin |
| `git_sha` | pipeline commit that produced the sqlite |
| detector ids / revisions | whatever writes `snr`, `singing_prob`, `content_type` |

Today's corpus `runs` row (for comparison when re-pinning, not a TASK-9 number): `asr_model=qwen3-asr-flash`, `aligner_model=Qwen/Qwen3-ForcedAligner-0.6B`, `jyutping_model=hon9kon9ize/wav2vec2bert-jyutping`, `tojyutping_version=3.2.0`, pipeline `git_sha=29379ae2cbfc7a454ff573341db891cb26777f6e`. Changing any of these is a new corpus.

## Re-pin in this analysis repo (repair PR, after the sqlite exists)

1. Tom approves the rebuild (this file is not approval).
2. Pipeline writes the new sqlite **outside** this repo.
3. One `repair/` PR updates `data/corpus_v2.sqlite`, `README.md` sha256 (and size), and every `status: closed` brief's `corpus_sha:` to the new pin.
4. Live closed tasks must still replay on the new corpus; a stamp mismatch makes them STALE (`LOOP.md`).
5. Do not edit TASK-6/7/8 **numbers** in that same PR if the repair is only a pin walk-through; follow contract clause 6 / `BAR-CHANGE:` if a bar must move.

## Requires

- [ ] Tom written approval to rebuild
- [ ] Pipeline pins listed above committed in the pipeline repo
- [ ] Detector versions for SNR / singing / content_type listed
- [ ] No download from a `cantoai-analysis` Cloud Agent
- [ ] No `data/` write until the repair PR
- [ ] Campaign index (`README.md` in this folder) updated to point at the new pin **after** that repair lands

Until then, TASK-9 is the pin-unchanged diagnostic.
