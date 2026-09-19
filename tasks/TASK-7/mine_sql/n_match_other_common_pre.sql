WITH
title_hit(tok) AS (
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
glyph_n AS (
  SELECT char AS g, COUNT(*) AS n_occ
  FROM syllables
  GROUP BY char
  HAVING COUNT(*) >= 10
)
SELECT COUNT(*)
FROM windows AS w
INNER JOIN syllables AS s ON s.uid = w.uid
INNER JOIN videos AS v ON v.video_id = w.video_id
INNER JOIN glyph_n AS g ON g.g = s.char
WHERE w.tier IN ('A', 'B')
  AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(v.upload_date, 1, 4) <= '2024'
  AND v.title IS NOT NULL
  AND length(v.title) > 0
  AND NOT EXISTS (
    SELECT 1 FROM title_hit AS t WHERE instr(v.title, t.tok) > 0
  )
  AND s.jp_realized IS NOT NULL
  AND length(s.jp_realized) > 0
  AND s.dur > 0
  AND s.jp_match IN ('exact_alt', 'exact_default')
