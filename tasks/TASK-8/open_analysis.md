# TASK-8 open analysis

Population: the 567 videos of this channel. Agreement is
n_match / n_judgeable on the contract-24 judgeable set; this task
does not re-declare that rate. Shares below use the judgeable
denominator of that period only.

## Class shares on the judgeable set

gap_share_<class>_pp = 100 * (share_post - share_pre), in percentage
points. Each class is an explicit jp_match predicate, not the
complement of the others. Unassigned judgeable rows (exact_default,
exact_alt, and any undeclared value) are counted in manifest.json.

- tone: share_pre=0.07226968 (n=7555 / 104539), share_post=0.10808948 (n=3764 / 34823), gap_share_tone_pp=3.58198018
- segment: share_pre=0.04530367 (n=4736 / 104539), share_post=0.08548948 (n=2977 / 34823), gap_share_segment_pp=4.01858088
- diff: share_pre=0.00745176 (n=779 / 104539), share_post=0.02193952 (n=764 / 34823), gap_share_diff_pp=1.44877583

tone+segment contribution = 7.60056106 pp; diff = 1.44877583 pp.
Sum of three contributions = 9.04933689 pp.

descriptive=1 for the share table (the three gap_share_*_pp values
are the declared measurements; this paragraph does not add a p-value).

## Contract-24 counts (not declared numbers)

- pre: {"n_dur_le_0": 16887, "n_empty_and_zerodur": 356, "n_empty_realized": 1138, "n_judgeable": 104539, "n_match": 91469, "n_total": 122208}
- post: {"n_dur_le_0": 6973, "n_empty_and_zerodur": 356, "n_empty_realized": 1045, "n_judgeable": 34823, "n_match": 27318, "n_total": 42485}

n_dur_le_0 is the count dropped by dur > 0 on the published set
of that period (contract 25). n_empty_realized and n_dur_le_0
overlap, so n_judgeable is not n_total minus those two counts.

## none on the published set (denominator is A+B, not judgeable)

- none_pre=1138 / n_total_pre=122208
- none_post=1045 / n_total_post=42485
- none on the judgeable set is structurally 0.

## Class-partition unassigned and undeclared enum on judgeable rows

- unassigned_class_pre=91469
- unassigned_class_post=27318
- undeclared_enum_pre=0
- undeclared_enum_post=0
- n_unassigned_period (videos)=0

## Year cells (video counts; 2021 and 2023 are small)

- 2021: n_videos=9
- 2022: n_videos=193
- 2023: n_videos=36
- 2024: n_videos=153
- 2025: n_videos=138
- 2026: n_videos=38

## Cluster bootstrap

B=2000 whole-video_id resamples within period strata.
Master seed 20260919. Per-stratum seeds are
int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16).

- pre: G_h=391, videos with judgeable syllables=389, ci_unreliable stratum=0
- post: G_h=176, videos with judgeable syllables=176, ci_unreliable stratum=0
- any-stratum ci_unreliable=0
- m=3

- tone: 95% percentile CI [1.893879, 5.226765] pp; includes 0=False; p_raw=0; p_BH=0; conclusion=estimated
- segment: 95% percentile CI [3.094654, 4.979467] pp; includes 0=False; p_raw=0; p_BH=0; conclusion=estimated
- diff: 95% percentile CI [1.030155, 1.940660] pp; includes 0=False; p_raw=0; p_BH=0; conclusion=estimated

## Conclusion

On the 567 videos of this channel, the judgeable A+B share of tone and of segment each rose after 2024 by more than the share of diff (gap_share_tone_pp=3.5820, gap_share_segment_pp=4.0186, gap_share_diff_pp=1.4488); the pre−post rise in disagreement quality on the judgeable set is larger in tone and segment than in diff.
