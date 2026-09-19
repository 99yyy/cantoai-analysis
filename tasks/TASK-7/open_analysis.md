# TASK-7 open analysis

Population: the 567 videos of this channel. The statistic is agreement
between the acoustic Jyutping and the dictionary, not a human label.
Film vs other is a title proxy, not a content judgement.

## Cell

Published A+B syllables whose video is `other` (title nonempty and
contains none of the TASK-6 title-proxy markers) and whose `char`
occurs at least 10 times on the full `syllables` table (every tier).
Agreement uses the contract-24 judgeable set (`jp_realized` nonempty
and `dur > 0`). `n_match` is counted only on that judgeable set.

- agree_other_common_pre = 0.888484 (n_match=76582, n_judgeable=86194)
- agree_other_common_post = 0.815181 (n_match=13457, n_judgeable=16508)
- gap_other_common_pp = 7.3304 = 100 * (agree_other_common_pre - agree_other_common_post)

Contract-24 counts for this cell are in `manifest.json`.
Worker `gap_other_common_pp` is `derived:` from the two agreement rates.

## Cluster bootstrap

B=2000 whole-`video_id` resamples within period strata.
Master seed 20260919. Per-stratum seeds are
`int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16)`.

G_h (videos per period, census of the 567 videos of this channel):

- `pre`: G_h=391, N_h=391, n_h_judgeable=86194, videos with judgeable syllables=330, ci_unreliable=0
- `post`: G_h=176, N_h=176, n_h_judgeable=16508, videos with judgeable syllables=116, ci_unreliable=0

Gap 95% percentile CI: [4.6207, 10.0956] pp.
p_raw=0, p_BH=0, m=1.
ci_unreliable (any stratum)=0; conclusion=estimated.
Interval includes 0: false.

Year cells (do not read 2021 or 2023 as a trend): 2021 n=9, 2022 n=193, 2023 n=36, 2024 n=153, 2025 n=138, 2026 n=38.

## Conclusion

On the 567 videos of this channel, agreement on judgeable A+B syllables that are other (title proxy) and common (full-table frequency ≥ 10) still falls after 2024, and the video_id-cluster 95% interval does not include 0.

Cell agreement counts:
- pre: {"n_dur_le_0": 13655, "n_empty_and_zerodur": 258, "n_empty_realized": 837, "n_judgeable": 86194, "n_match": 76582, "n_total": 100428}
- post: {"n_dur_le_0": 3089, "n_empty_and_zerodur": 121, "n_empty_realized": 345, "n_judgeable": 16508, "n_match": 13457, "n_total": 19821}
