# TASK-7 audit

Path: `tasks/TASK-7/audit.md` (LOOP names `review/TASK-7/audit.md`; that directory is outside chore `CHORE_ALLOW`, and an agent branch cannot edit the brief this Draft close needs).

Range: `ae9b293` (brief open, #77) through `a553d03` (worker #79 on main after verifier #78). This close does not re-judge the 10 `output-check` values; `./verify task 7` on `a553d03` printed `TASK-7 [open]: 10/10 number(s) agree`.

Verdict recorded in `tasks/TASK-7/RESULT.json`: **supported**. The brief's falsifier was a video-cluster 95% CI that includes 0; worker `bootstrap.json` reports [4.6207, 10.0956] pp with `ci_unreliable_any=0`, `B=2000`. That interval is open analysis, not a declared number. The auditor did not re-run the bootstrap and did not import `tasks/TASK-7/run_worker.py`.

## Independent recompute (key number)

Corpus pin checked first: sha256 `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f` matches `README.md`. Minimal SQL against `data/corpus_v2.sqlite` (read-only; not a worker/verifier file):

```sql
WITH
film_markers(tok) AS (
  SELECT '粵劇' UNION ALL SELECT '任劍輝' UNION ALL SELECT '芳艷芬'
  UNION ALL SELECT '李小龍' UNION ALL SELECT '林鳳' UNION ALL SELECT '吳楚帆'
  UNION ALL SELECT '石堅' UNION ALL SELECT '謝賢' UNION ALL SELECT '新馬師曾'
  UNION ALL SELECT '白雪仙'
),
common AS (
  SELECT char AS glyph FROM syllables GROUP BY char HAVING COUNT(*) >= 10
),
cell AS (
  SELECT
    CASE
      WHEN substr(v.upload_date,1,4) GLOB '[0-9][0-9][0-9][0-9]'
       AND substr(v.upload_date,1,4) <= '2024' THEN 'pre'
      WHEN substr(v.upload_date,1,4) GLOB '[0-9][0-9][0-9][0-9]'
       AND substr(v.upload_date,1,4) >= '2025' THEN 'post'
    END AS period,
    s.jp_match AS jp_match
  FROM syllables AS s
  JOIN windows AS w ON w.uid = s.uid
  JOIN videos AS v ON v.video_id = s.video_id
  JOIN common AS c ON c.glyph = s.char
  WHERE w.tier IN ('A','B')
    AND v.title IS NOT NULL AND v.title <> ''
    AND NOT EXISTS (SELECT 1 FROM film_markers AS m WHERE instr(v.title, m.tok) > 0)
    AND s.jp_realized IS NOT NULL AND s.jp_realized <> ''
    AND s.dur > 0
),
agg AS (
  SELECT
    period,
    COUNT(*) AS n_judgeable,
    SUM(CASE WHEN jp_match IN ('exact_default','exact_alt') THEN 1 ELSE 0 END) AS n_match
  FROM cell
  WHERE period IS NOT NULL
  GROUP BY period
)
SELECT
  (SELECT n_judgeable FROM agg WHERE period='pre'),
  (SELECT n_match FROM agg WHERE period='pre'),
  (SELECT n_judgeable FROM agg WHERE period='post'),
  (SELECT n_match FROM agg WHERE period='post'),
  100.0 * (
    (SELECT 1.0*n_match/n_judgeable FROM agg WHERE period='pre')
    -
    (SELECT 1.0*n_match/n_judgeable FROM agg WHERE period='post')
  );
```

Result: 86194, 76582, 16508, 13457, **7.33035986874696**. Same as `gap_other_common_pp` in `results.json` and `mine.json`. `EXPLAIN QUERY PLAN` SCANs `syllables` and SEARCHes `windows` / `videos`.

Worker gap is `derived:` from the two agreement rates (`a553d03` `tasks/TASK-7/results.json`). Verifier gap is direct SQL (`478fb19` `tasks/TASK-7/mine_sql/gap_other_common_pp.sql`). Film-token lists match the brief; implementations differ (worker `UNION ALL` markers vs verifier `VALUES`).

## Two ways the supported conclusion can still be wrong

1. **Title proxy, not content.** `other` is a nonempty title that contains none of ten film-name tokens. A post-2024 change in how videos are titled (or a shift toward talk/song/classroom mix that never uses those names) moves mass in or out of the cell without any change in dictionary agreement on a stable “ordinary speech” population. Manifest `drop_film_proxy` removes 18172 of 122208 pre published syllables and 21848 of 42485 post — post is much more film-titled, so the other cell is the remainder of a heuristic, not a genre.

2. **Common is corpus frequency, not everyday words.** Common is `char` count ≥ 10 on the full `syllables` table, every tier, including unpublished rows. That class can still mix easy particles with names and loan-character spellings. TASK-6 already found rare share fell; landing the leftover drop inside this cell does not show the cell is homogeneous. A few long videos can dominate the syllable-weighted point estimate (post has 116 videos with judgeable syllables in the cell out of G_h=176). The CI clusters on `video_id`, which addresses that for the interval the worker reported, not for the claim that “ordinary non-film characters” got harder.

Further limits (not a third mechanism, same caveats): `dur > 0` is part of judgeable, so aligner zeros (contract: 14.4% of syllables) are outside the rate; this cell’s `n_dur_le_0` is 13655 pre / 3089 post. Year cells 2021 n=9 and 2023 n=36 must not be read as a trend. Population is the 567 videos of this channel.

## Process notes (not findings that move a bar)

No bar moved: brief fences for `numbers` / `n` / `frame` / `identities` are unchanged in this close; only `status:` and `corpus_sha:` are added. Worker and verifier started from `ae9b293`; #78 wrote only `mine.json` + `mine_sql/`; #79 wrote `results.json` + `sql/` + open-analysis companions. Squash merges on main are both authored `Tomy <yan325128@gmail.com>`; this PR does not introduce either output file, so the author-independence clause does not re-fire. Phrase “not supported” does not appear in the worker conclusion.
