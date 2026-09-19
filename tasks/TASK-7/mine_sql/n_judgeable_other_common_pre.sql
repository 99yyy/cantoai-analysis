WITH
marker(tok) AS (
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
freq AS (
  SELECT char AS glyph, COUNT(*) AS occ
  FROM syllables
  GROUP BY char
),
pre_other AS (
  SELECT v.video_id
  FROM videos AS v
  WHERE substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(v.upload_date, 1, 4) <= '2024'
    AND v.title IS NOT NULL
    AND length(v.title) > 0
    AND NOT EXISTS (
      SELECT 1 FROM marker AS m WHERE instr(v.title, m.tok) > 0
    )
)
SELECT COUNT(*)
FROM syllables AS s
INNER JOIN windows AS w ON w.uid = s.uid
INNER JOIN pre_other AS p ON p.video_id = w.video_id
INNER JOIN freq AS f ON f.glyph = s.char
WHERE w.tier IN ('A', 'B')
  AND f.occ >= 10
  AND s.jp_realized IS NOT NULL
  AND length(s.jp_realized) > 0
  AND s.dur > 0
