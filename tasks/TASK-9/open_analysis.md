# TASK-9 open analysis

Population: the 567 videos of this channel. Declared numbers
are published-window proxies (windows.tier IN ('A','B')), not
judgeable-syllable agreement, and not jp_match class shares.

## Window-weighted rates (declared)

- rate_flag_sing_pre_pm=0.00000000 (n_flag_sing_pre=0 / n_windows_pre=3286)
- rate_flag_sing_post_pm=0.00000000 (n_flag_sing_post=0 / n_windows_post=1153)
- gap_flag_sing_pm=0.00000000 = rate_flag_sing_post_pm - rate_flag_sing_pre_pm
- rate_coverage_pre_pm=900.03864881
- rate_coverage_post_pm=882.85082394
- gap_coverage_pm=-17.18782488 = rate_coverage_post_pm - rate_coverage_pre_pm

These two gaps are not definitionally equal to any closed task's
total gap (TASK-6 gap_contract_pp, TASK-7 gap_other_common_pp, or
TASK-8 share gaps). The window-weighted formula is each proxy's
own post − pre. vidmed / trim10 reweight or subsample the same
gap; they are not extra decomposition terms.

coverage is not a proportion and this task does not define a higher
or lower coverage mean as better or worse.

## Tier filter (contract 23 / 27)

- windows dropped by windows.tier not in A+B: 472
- among dropped windows, flag_sing=1: 14
- published A+B windows: 4439
- published A+B windows with flag_sing=1: 0

The tier rule already removes every flag_sing=1 window in this
corpus. A published-set flag_sing rate of 0 is not the same as
the channel having no singing-flag windows.

## Year cells (inquiry Q1; descriptive=1)

Natural unit of upload_date is calendar year substr(upload_date,1,4).
2021 and 2023 are small cells and are not a trend.

- 2021: n_videos=9, n_windows=157, rate_flag_sing_pm=0.00000000, rate_coverage_pm=926.30573248 (descriptive=1)
- 2022: n_videos=193, n_windows=2008, rate_flag_sing_pm=0.00000000, rate_coverage_pm=907.73605578 (descriptive=1)
- 2023: n_videos=36, n_windows=233, rate_flag_sing_pm=0.00000000, rate_coverage_pm=886.79399142 (descriptive=1)
- 2024: n_videos=153, n_windows=888, rate_flag_sing_pm=0.00000000, rate_coverage_pm=881.46396396 (descriptive=1)
- 2025: n_videos=138, n_windows=904, rate_flag_sing_pm=0.00000000, rate_coverage_pm=885.99225664 (descriptive=1)
- 2026: n_videos=38, n_windows=249, rate_flag_sing_pm=0.00000000, rate_coverage_pm=871.44578313 (descriptive=1)
- unassigned: n_videos=0, n_windows=0 (no published-window rates; descriptive=1)

## Q2 three-column table: flag_sing

- gap_flag_sing_pm=0.00000000
- gap_flag_sing_vidmed_pm=0.00000000
- gap_flag_sing_trim10_pm=0.00000000

Period rates used to recompute:
- window-weighted rate_flag_sing_pre_pm=0.00000000, rate_flag_sing_post_pm=0.00000000
- vidmed rate_flag_sing_pre_vidmed_pm=0.00000000, rate_flag_sing_post_vidmed_pm=0.00000000 (n_videos_pre=389, n_videos_post=176; not declared numbers)
- trim10 window-weighted rate_flag_sing_pre_pm=0.00000000, rate_flag_sing_post_pm=0.00000000 (remaining n_windows_pre=2931, n_windows_post=1100)

Q2 2x/sign rule did not trigger for flag_sing (all three point values are 0).

## Q2 three-column table: coverage

- gap_coverage_pm=-17.18782488
- gap_coverage_vidmed_pm=-22.00000000
- gap_coverage_trim10_pm=-19.25035710

Period rates used to recompute:
- window-weighted rate_coverage_pre_pm=900.03864881, rate_coverage_post_pm=882.85082394
- vidmed rate_coverage_pre_vidmed_pm=889.50000000, rate_coverage_post_vidmed_pm=867.50000000
- trim10 window-weighted rate_coverage_pre_pm=898.60982173, rate_coverage_post_pm=879.35946463 (remaining n_windows_pre=2973, n_windows_post=1046)

Q2 2x/sign rule did not trigger for coverage.
If any two of window / vidmed / trim10 differ in sign or have
absolute-value ratio > 2 (including one 0 and one non-0), the
conclusion may not be written as an overall change.

Window median coverage (descriptive=1, no p-value, no median gap
declared):
- rate_coverage_median_pre_pm=988.00000000
- rate_coverage_median_post_pm=982.00000000

## Bias direction (inquiry Q5)

flag_sing is a model flag proxy, not a content judgement and not
a title-keyword class. 把非唱窗标成唱，会把 gap_flag_sing_pm 往正
（迎合假说）推；把唱窗漏标，会往负推。

## Cluster bootstrap (window-weighted gaps only; m=2)

B=2000 whole-video_id resamples within period strata.
Master seed 20260920. Per-stratum seeds are
int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16).

- pre: G_h=391, videos with published A+B windows=389, ci_unreliable stratum=0
- post: G_h=176, videos with published A+B windows=176, ci_unreliable stratum=0
- any-stratum ci_unreliable=0
- m=2

- gap_flag_sing_pm: 95% percentile CI [0.000000, 0.000000] pm; includes 0=True; p_raw=1; p_BH=1; conclusion=estimated
- gap_coverage_pm: 95% percentile CI [-29.294763, -5.579667] pm; includes 0=False; p_raw=0.002; p_BH=0.004; conclusion=estimated

vidmed and trim10 are descriptive=1 for inference: they are not
in m and do not carry p-values.

## Optional descriptive=1 (not declared)

- chars_per_sec mean pre=2.65100426, post=2.79909801
- videos.speech_s / n_windows mean pre=13.04138003, post=11.22865372
- window dur mean pre=13.20451491, post=12.40735473
- boundary_start shares on published windows: {'pause': 0.7965758053615679, 'bof': 0.11489074115791845, 'short_gap': 0.08853345348051363}
- boundary_end shares on published windows: {'pause': 0.7850867312457761, 'eof': 0.12615453931065557, 'short_gap': 0.08875872944356837}
- aligned=1 on every window in this corpus; it separates nothing.

## Conclusion

On the 567 videos of this channel, published A+B windows do not carry a higher flag_sing per-mille after 2024 (gap_flag_sing_pm=0.0000; window/vidmed/trim10 all 0; 14 flag_sing=1 windows were already removed by the A+B tier whitelist). Coverage mean moved by gap_coverage_pm=-17.1878 pm (post lower; coverage window-weighted 95% cluster interval excludes 0; Q2 window=-17.1878, vidmed=-22.0000, trim10=-19.2504). post flag_sing per-mille is not higher than pre on published windows. Coverage is unsigned as quality in this brief, so the coverage mean shift is not a claim that post windows are worse.
