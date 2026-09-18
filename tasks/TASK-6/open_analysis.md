# TASK-6 open analysis

Population: the 567 videos of this channel. The statistic is agreement
between the acoustic Jyutping and the dictionary, not a human label.

## Decomposition

Covariates (none written by this run):

- `film` vs `other`: title-proxy markers from `videos.title` (粵劇, 任劍輝,
  芳艷芬, 李小龍, 林鳳, 吳楚帆, 石堅, 謝賢, 新馬師曾, 白雪仙). This is a title
  proxy, not a content judgement.
- Rare characters: `char` with frequency < 10 in the full `syllables` table
  (every tier). Used only to check composition; it is not the residual's
  standardizing variable.

`tier`, `coverage`, `chars_per_sec` and `aligned` were not used as
stratifiers, so the unstratified contract gap is the baseline gap.

Standardization: Kitagawa / post-stratification of post rates onto the
pre period's film/other mix of judgeable syllables. The reported film
comparison is the difference-in-differences versus the `other` title-proxy
group, not the raw film gap.

- Unadjusted contract gap: 9.0493 pp
  (pre agreement 0.874975, post 0.784482).
- Film title-proxy: pre 0.821247, post 0.758287.
- Other title-proxy: pre 0.884191, post 0.811401.
- DID (film gap minus other gap): -0.9830 pp.
- Pre film share of judgeable syllables: 0.146414.
- Post agreement if post had the pre film mix: 0.803624.
- Composition (explained): 1.9143 pp.
- Residual (pre minus composition-adjusted post): 7.1351 pp.

Rare-character share is slightly lower after 2024, so a shift toward rare
characters does not explain the drop
 (pre 0.034499, post 0.031870).

Contract-24 period totals live in `manifest.json` (and the named counts
in `results.json`).

## Residual gap, cluster bootstrap

B=2000 whole-`video_id` resamples within film×period strata.
Master seed 20250918. Per-stratum seeds are
`int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16)`.

G_h (videos per stratum, census of the 567 videos of this channel):

- `film_pre`: G_h=59, N_h=59, n_h_judgeable=15306, videos with judgeable syllables=59, ci_unreliable=0
- `film_post`: G_h=60, N_h=60, n_h_judgeable=17649, videos with judgeable syllables=60, ci_unreliable=0
- `other_pre`: G_h=332, N_h=332, n_h_judgeable=89233, videos with judgeable syllables=330, ci_unreliable=0
- `other_post`: G_h=116, N_h=116, n_h_judgeable=17174, videos with judgeable syllables=116, ci_unreliable=0

Residual 95% percentile CI: [4.5998, 9.6243] pp.
p_raw=0, p_BH=0, m=1.
ci_unreliable (any stratum)=0; conclusion=estimated.

Year cells (do not read 2021 or 2023 as a trend): 2021 n=9, 2022 n=193, 2023 n=36, 2024 n=153, 2025 n=138, 2026 n=38.

## Hypothesis

What data, what comparison, what result would refute it: among judgeable
A+B syllables whose `char` occurs at least 10 times in the full corpus
and whose video is in the `other` title-proxy group, the video_id-cluster
bootstrap 95% CI (B>=1000, strata = period) of agreement(pre) −
agreement(post) includes 0. That result would refute the claim that the
residual drop is a within-inventory rise in tone/segment disagreement on
ordinary characters in non-film titles.

## Conclusion

On the 567 videos of this channel, the title-proxy film mix accounts for
only a minority of the post-2024 agreement drop; the residual remains
after reweighting post rates to the pre film mix and sits in tone and
segment disagreements rather than in rare-character share.
