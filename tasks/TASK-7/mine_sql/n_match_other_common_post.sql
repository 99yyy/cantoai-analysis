WITH
proxy(needle) AS (
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
kept_char AS (
  SELECT char AS ch
  FROM syllables
  GROUP BY 1
  HAVING COUNT(*) >= 10
)
SELECT SUM(
  CASE
    WHEN syl.jp_match = 'exact_default' OR syl.jp_match = 'exact_alt'
    THEN 1
    ELSE 0
  END
)
FROM syllables AS syl
JOIN kept_char AS kc ON kc.ch = syl.char
JOIN windows AS win ON win.uid = syl.uid
JOIN videos AS vid ON vid.video_id = win.video_id
WHERE (win.tier = 'A' OR win.tier = 'B')
  AND substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(vid.upload_date, 1, 4) >= '2025'
  AND vid.title IS NOT NULL
  AND length(vid.title) > 0
  AND NOT EXISTS (
    SELECT 1 FROM proxy AS p WHERE instr(vid.title, p.needle) > 0
  )
  AND syl.jp_realized IS NOT NULL
  AND syl.jp_realized <> ''
  AND syl.dur > 0
