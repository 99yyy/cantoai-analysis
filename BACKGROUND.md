# BACKGROUND

Why this repository exists, what the data is, and which words to use. This is
the only file here that explains rather than instructs. Read it first.

## Read this much, in this order

| file | answers |
|---|---|
| `BACKGROUND.md` | what this is, what the columns mean, which words to use |
| `.cursor/rules/analysis-contract.mdc` | analysis assertions. It overrides every task brief |
| `LOOP.md` | the only execution playbook: who computes, who checks, what merges. If other docs conflict, LOOP.md wins |
| `tasks/TASK-N.md` | what you owe, and the tolerance on each number |
| `README.md` | the corpus path and its sha256 |

Nothing else here is an instruction. `src/`, `tests/` and anything under
`tasks/TASK-N/` are previous outputs; they are not a specification, and a task
that produced them is not your task.

## What this is

One YouTube channel of Cantonese speech, 567 videos. A pipeline transcribed the
audio, cut it into windows, aligned each window to its text syllable by
syllable, and gave every syllable two Jyutping readings: one looked up in a
dictionary, one predicted by an acoustic model. Where the two disagree,
something is wrong — but the corpus cannot say which side.

**There is no human transcription anywhere in it.** `verification_status` is
NULL on all 171,867 syllable rows. Nothing here has been listened to and
labelled by a person.

That is the whole reason the measured quantity is called **agreement** and never
accuracy. Two fallible readers agreeing is evidence; neither is ground truth,
and a number computed from `jp_match` cannot tell you which one erred.

The standing question is why agreement is lower on material uploaded from 2025
onward, and how much of that gap is explained by things the corpus already
records rather than by a change in the speech or in the models.

## How the corpus was made

Audio was downloaded per video and segmented into windows, each with its own
sample range and duration. An ASR model produced `text_raw`, which was
normalised into `text_norm` and then `text_clean`; a language tag was assigned
per window. A forced aligner placed every character of `text_clean` on the audio,
producing the `syllables` rows — `c0` is the character's offset into
`text_clean`, and `pos` its index within the window. A dictionary supplied
`jp_default`, the in-context reading `jp_ctx`, and the candidate set
`jp_candidates` / `n_cand`. An acoustic model supplied `jp_realized`. Comparing
the two produced `jp_match`. A tier was assigned per window as a quality grade.

The models are pinned in the `runs` table (`asr_model`, `aligner_model`,
`jyutping_model`, `tojyutping_version`) together with the pipeline's git sha.
**They are not re-run here.** This repository analyses one frozen corpus; it
does not contain the pipeline, the audio, or any model weights, and no task will
ask you to produce them.

## The columns, and which of them are being judged

`videos` (567) → `windows` (4,911) → `syllables` (171,867). A window joins to
its video on `video_id`; a syllable joins to its window on `uid`, and carries
`video_id` as well. `tier` appears on both `windows` and `syllables` and agrees
on every row.

**Recorded or derived from text** — `video_id`, `title`, `upload_date`
(YYYYMMDD as text), `n_windows`, `speech_s`; `uid`, `idx`, `start`, `end`,
`dur`, `start_sample`, `end_sample`, `text_raw`, `text_norm`, `text_clean`,
`n_syllables`; `syl_id`, `pos`, `c0`, `char`, `prev_char`, `next_char`, `ctx`.

**Dictionary side** — `jp_default`, `jp_ctx`, `jp_candidates`, `n_cand`.

**Model outputs, i.e. the things being assessed or produced by the assessment**
— `jp_realized`, `jp_match`, `tier`, `coverage`, `chars_per_sec`, `aligned`,
`lang`, `in_range`, `max_zero_run`, `tone_shift_suspect`, the `flag_*` columns,
`review_prior`, and the syllable timings `start` / `end` / `dur`.

The split matters because stratifying by a model output partly measures the rule
that made it rather than the phenomenon (contract clause 27). Four specifics
worth knowing before you reach for one:

- `aligned` is `1` on every window. It separates nothing.
- `coverage` is not a proportion; it runs well above 1. Look at its distribution
  before treating it as one.
- `review_prior` is partly determined by `jp_match`, so it may not stratify,
  filter or weight anything computed from `jp_match` (clause 26).
- `verification_status` and `verification_note` are empty on every row. They are
  placeholders for human review that has not happened.

`jp_match` takes six values: `exact_default` and `exact_alt` (the model's
reading matches the dictionary's default, or one of its alternatives) count as
agreement; `tone`, `segment`, `diff` and `none` do not. `none` means the model
produced no reading at all, and those rows have an empty `jp_realized`.

## Words that are not optional

- **agreement**, never accuracy, and never "error rate".
- The population is **"the 567 videos of this channel"**. Never "Cantonese",
  never "Cantonese speakers".
- **pp** is percentage points; **pm** is per mille.
- **judgeable** is defined in contract clause 24. A syllable that is not
  judgeable is excluded from both the numerator and the denominator, never from
  one alone.
- The film/other split is a **title proxy**: it matches keywords in
  `videos.title`. It is not a judgement about what the video contains, and any
  conclusion using it says so.

## Directions already settled

Do not re-propose these; they were decided and the reasons are in the contract.

- Alignment is not re-run, and no model version is changed. Zero-width syllable
  durations are a documented property of this aligner, not damage to repair
  (clause 25).
- Syllable onsets are usable; syllable durations are not, beyond the `dur > 0`
  test that clause 24 already builds in.
- There is no human-labelled subset to validate against, so no task can be
  answered by "compare to ground truth".

## What this file deliberately does not contain

No results. No figure that any task's `numbers` block declares, and no
conclusion from any earlier task stated as fact.

That is not an oversight. Two agents answer the same brief from the same
starting point without seeing each other, and CI compares what they hand in. A
number you could have read here is a number you would not have computed, and
two agents copying one number is not agreement. If you find yourself wanting a
previous result in order to proceed, you do not need it — compute it.

## When you cannot proceed

Write `BLOCKED: <one line>` in the pull-request body and stop. Do not relax a
threshold, edit an assertion, special-case an input, or guess at a definition
the brief did not give. A red check is information; work out what it found.
