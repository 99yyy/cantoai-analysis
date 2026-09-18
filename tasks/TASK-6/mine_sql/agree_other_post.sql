WITH token(t) AS (
  SELECT '粵劇' UNION ALL SELECT '任劍輝' UNION ALL SELECT '芳艷芬' UNION ALL SELECT '李小龍' UNION ALL SELECT '林鳳' UNION ALL SELECT '吳楚帆' UNION ALL SELECT '石堅' UNION ALL SELECT '謝賢' UNION ALL SELECT '新馬師曾' UNION ALL SELECT '白雪仙'
),
marked AS (
  SELECT DISTINCT vid0.video_id AS video_id
  FROM videos AS vid0
  JOIN token ON instr(vid0.title, token.t) > 0
)
SELECT CAST(SUM(CASE WHEN sy.jp_match IN ('exact_default', 'exact_alt') THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
FROM windows AS win
JOIN syllables AS sy ON sy.uid = win.uid
JOIN videos AS vid ON vid.video_id = win.video_id
LEFT JOIN marked ON marked.video_id = vid.video_id
WHERE win.tier IN ('A', 'B')
  AND (substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]' AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) >= 2025)
  AND (sy.jp_realized IS NOT NULL AND length(sy.jp_realized) > 0 AND sy.dur > 0)
  AND marked.video_id IS NULL
  AND vid.title IS NOT NULL
  AND length(vid.title) > 0
