WITH
old_film(needle) AS (
  SELECT '粵劇' UNION ALL
  SELECT '任劍輝' UNION ALL
  SELECT '芳艷芬' UNION ALL
  SELECT '李小龍' UNION ALL
  SELECT '林鳳' UNION ALL
  SELECT '吳楚帆' UNION ALL
  SELECT '石堅' UNION ALL
  SELECT '謝賢' UNION ALL
  SELECT '新馬師曾' UNION ALL
  SELECT '白雪仙'
),
common_set AS (
  SELECT char
  FROM syllables
  GROUP BY char
  HAVING COUNT(*) >= 10
)
SELECT COUNT(*)
FROM syllables AS syl
JOIN windows AS win ON win.uid = syl.uid
JOIN videos AS vid ON vid.video_id = syl.video_id
JOIN common_set AS com ON com.char = syl.char
WHERE win.tier IN ('A', 'B')
  AND substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(vid.upload_date, 1, 4) >= '2025'
  AND vid.title IS NOT NULL
  AND length(vid.title) > 0
  AND NOT EXISTS (
    SELECT 1 FROM old_film AS f WHERE instr(vid.title, f.needle) > 0
  )
  AND syl.jp_realized IS NOT NULL
  AND syl.jp_realized <> ''
  AND syl.dur > 0
