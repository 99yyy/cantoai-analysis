# TASK-8 audit

Range: `4cf5b74` (brief open, #84) through `a422065` (worker #86 on main after verifier #85). `origin/main` at this write is `a422065`. This audit does not re-judge the 14 `output-check` values; `./verify task 8` on `a422065` printed `TASK-8 [open]: 14/14 number(s) agree`.

LOOP requires `review/TASK-N/audit.md`. Agent branches cannot edit the brief (`no_brief`). Chore cannot write `review/` (`CHORE_ALLOW`). This close uses `repair/` so the stamp, RESULT, and LOOP audit path can land together without widening DENY or CHORE_ALLOW. SCOPE_ACTOR on the TASK-7 repair close was `99yyy`.

Verdict in `tasks/TASK-8/RESULT.json`: **supported**. The brief's open-analysis question is whether the judgeable-set rise in disagreement quality concentrates in `tone` and/or `segment` rather than mainly in `diff`. Independent SQL below reproduces `gap_share_tone_pp = 3.5819801831625573`, `gap_share_segment_pp = 4.018580877255639`, `gap_share_diff_pp = 1.4487758315949515`. Tone+segment (~3.58 + ~4.02) dominate diff (~1.45). Worker bootstrap CIs (open analysis, not replayed here) exclude 0 for all three with `ci_unreliable=0`. The auditor did not re-run the bootstrap and did not import `tasks/TASK-8/run_worker.py`.

## Independent recompute (key number)

Corpus pin checked first: sha256 `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f` matches `README.md`. Minimal SQL against `data/corpus_v2.sqlite` (read-only; not a worker/verifier file):

```sql
WITH
pub AS (
  SELECT s.jp_match, s.jp_realized, s.dur,
         substr(v.upload_date, 1, 4) AS y4
  FROM syllables AS s
  JOIN windows AS w ON w.uid = s.uid
  JOIN videos AS v ON v.video_id = s.video_id
  WHERE w.tier IN ('A', 'B')
),
cell AS (
  SELECT
    CASE
      WHEN y4 GLOB '[0-9][0-9][0-9][0-9]' AND y4 <= '2024' THEN 'pre'
      WHEN y4 GLOB '[0-9][0-9][0-9][0-9]' AND y4 >= '2025' THEN 'post'
    END AS period,
    jp_match, jp_realized, dur
  FROM pub
),
judge AS (
  SELECT period, jp_match
  FROM cell
  WHERE period IS NOT NULL
    AND jp_realized IS NOT NULL AND jp_realized <> ''
    AND dur > 0
),
agg AS (
  SELECT
    period,
    COUNT(*) AS n_judgeable,
    SUM(CASE WHEN jp_match = 'tone' THEN 1 ELSE 0 END) AS n_tone,
    SUM(CASE WHEN jp_match = 'segment' THEN 1 ELSE 0 END) AS n_segment,
    SUM(CASE WHEN jp_match = 'diff' THEN 1 ELSE 0 END) AS n_diff,
    SUM(CASE WHEN jp_match IS NULL THEN 1 ELSE 0 END) AS n_null
  FROM judge
  GROUP BY period
)
SELECT
  (SELECT n_judgeable FROM agg WHERE period='pre'),
  (SELECT n_judgeable FROM agg WHERE period='post'),
  (SELECT n_tone FROM agg WHERE period='pre'),
  (SELECT n_tone FROM agg WHERE period='post'),
  (SELECT n_segment FROM agg WHERE period='pre'),
  (SELECT n_segment FROM agg WHERE period='post'),
  (SELECT n_diff FROM agg WHERE period='pre'),
  (SELECT n_diff FROM agg WHERE period='post'),
  (SELECT n_null FROM agg WHERE period='pre'),
  (SELECT n_null FROM agg WHERE period='post'),
  100.0 * (
    (SELECT 1.0 * n_tone / n_judgeable FROM agg WHERE period='post')
    - (SELECT 1.0 * n_tone / n_judgeable FROM agg WHERE period='pre')
  ),
  100.0 * (
    (SELECT 1.0 * n_segment / n_judgeable FROM agg WHERE period='post')
    - (SELECT 1.0 * n_segment / n_judgeable FROM agg WHERE period='pre')
  ),
  100.0 * (
    (SELECT 1.0 * n_diff / n_judgeable FROM agg WHERE period='post')
    - (SELECT 1.0 * n_diff / n_judgeable FROM agg WHERE period='pre')
  );
```

Result: 104539, 34823, 7555, 3764, 4736, 2977, 779, 764, 0, 0, **3.5819801831625573**, **4.018580877255639**, **1.4487758315949515**. Same as the three `gap_share_*_pp` rows in `results.json` and `mine.json`. NULL `jp_match` on judgeable rows is 0. `EXPLAIN QUERY PLAN` SEARCHes `windows` on `i_win_tier`, `syllables` on `i_syl_uid`, and `videos` on the primary key.

Worker and verifier both route the three gaps as `derived:` from the eleven count SQLs (`5c7337e` `tasks/TASK-8/results.json`; `4b7f16f` `tasks/TASK-8/mine.json`). Implementations of the counts differ (worker `tier IN ('A','B')` + `CAST(... AS INTEGER)`; verifier `tier = 'A' OR tier = 'B'` + `y4 + 0`). The brief preferred one side querying the gap in SQL so the identities fence would fire; both sides used `derived:`, so output-check skipped those three identities. The derived routes still replay the same formula.

## Two ways the supported conclusion can still be wrong

1. **`jp_match` is a model label, not a pronunciation class.** `tone` / `segment` / `diff` are how the dictionary and aligner tagged the mismatch. A post-2024 change in candidate picking, forced-alignment, or dictionary defaults can move mass from `diff` into `tone` or `segment` (or the reverse) without any change in what was said. The hypothesis treats those tags as "disagreement quality."

2. **Share rise is a partition of the same drop, plus mix.** With undeclared enum = 0 on the judgeable set, `gap_share_tone_pp + gap_share_segment_pp + gap_share_diff_pp` equals the fall in exact-match share (here 9.049 pp, the same size as TASK-6 `gap_contract_pp`). That identity says the three classes exhaust the drop; it does not say why they rose. This task is all published A+B judgeable syllables, not the other×common cell. Post has 176 videos against 391 pre; film-titled mass is higher after 2024 (TASK-6). A few long post videos can lift syllable-weighted shares. Worker CIs cluster on `video_id` and exclude 0; that interval is open analysis.

Further limits (not a third mechanism, same caveats): `dur > 0` is part of judgeable, so aligner zeros (contract: 14.4% of syllables) are outside the shares; this frame's `n_dur_le_0` is 16887 pre / 6973 post. Year cells 2021 n=9 and 2023 n=36 must not be read as a trend. Population is the 567 videos of this channel. Phrase "not supported" does not appear in the worker conclusion.

## Process notes (not findings that move a bar)

No bar moved: brief fences for `numbers` / `n` / `frame` / `identities` are unchanged; only `status:` and `corpus_sha:` are added. Worker introducing commit `5c7337e` (author Cursor Agent) and verifier introducing commit `4b7f16f` (author Tomy, squash of #85) share parent `4cf5b74`; neither tree holds the other side's file; neither is an ancestor of the other. Repair `bc-601a160d-d073-5796-b958-1fdbc6f3d341` rewrote the worker commit off `4cf5b74` after a history-independence miss on the first worker push (`8786b59` was the same starting ref and also lacked `mine.json`). This PR does not introduce either output file, so the author-independence clause does not re-fire.
