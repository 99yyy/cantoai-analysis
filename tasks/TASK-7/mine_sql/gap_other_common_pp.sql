WITH
film_tok(tok) AS (
  VALUES
    ('粵劇'),
    ('任劍輝'),
    ('芳艷芬'),
    ('李小龍'),
    ('林鳳'),
    ('吳楚帆'),
    ('石堅'),
    ('謝賢'),
    ('新馬師曾'),
    ('白雪仙')
),
yyyy AS (
  SELECT
    video_id,
    title,
    substr(upload_date, 1, 4) AS yr
  FROM videos
),
common_glyph AS (
  SELECT char AS glyph
  FROM syllables
  GROUP BY char
  HAVING COUNT(*) >= 10
),
tagged AS (
  SELECT
    CASE
      WHEN y.yr GLOB '[0-9][0-9][0-9][0-9]' AND y.yr <= '2024' THEN 'pre'
      WHEN y.yr GLOB '[0-9][0-9][0-9][0-9]' AND y.yr >= '2025' THEN 'post'
    END AS period,
    s.jp_match,
    s.jp_realized,
    s.dur
  FROM syllables AS s
  JOIN windows AS w ON w.uid = s.uid
  JOIN yyyy AS y ON y.video_id = w.video_id
  JOIN common_glyph AS g ON g.glyph = s.char
  WHERE w.tier IN ('A', 'B')
    AND y.title IS NOT NULL
    AND length(y.title) > 0
    AND NOT EXISTS (
      SELECT 1 FROM film_tok AS t WHERE instr(y.title, t.tok) > 0
    )
),
cell AS (
  SELECT
    period,
    SUM(
      CASE
        WHEN jp_realized IS NOT NULL
         AND jp_realized <> ''
         AND dur > 0
        THEN 1.0
        ELSE 0.0
      END
    ) AS n_jud,
    SUM(
      CASE
        WHEN jp_realized IS NOT NULL
         AND jp_realized <> ''
         AND dur > 0
         AND jp_match IN ('exact_default', 'exact_alt')
        THEN 1.0
        ELSE 0.0
      END
    ) AS n_hit
  FROM tagged
  WHERE period IS NOT NULL
  GROUP BY period
)
SELECT 100.0 * (
  (SELECT n_hit / n_jud FROM cell WHERE period = 'pre')
  -
  (SELECT n_hit / n_jud FROM cell WHERE period = 'post')
)
