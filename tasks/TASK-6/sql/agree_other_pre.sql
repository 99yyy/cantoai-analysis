SELECT CAST(SUM(CASE WHEN s.jp_match IN ('exact_default', 'exact_alt') THEN 1 ELSE 0 END) AS REAL) / COUNT(*) AS value
FROM syllables s
JOIN windows w ON s.uid = w.uid
JOIN videos v ON s.video_id = v.video_id
WHERE w.tier IN ('A', 'B')
  AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(v.upload_date, 1, 4) <= '2024'
  AND v.title IS NOT NULL
  AND v.title != ''
  AND v.title NOT LIKE '%粵劇%'
  AND v.title NOT LIKE '%任劍輝%'
  AND v.title NOT LIKE '%芳艷芬%'
  AND v.title NOT LIKE '%李小龍%'
  AND v.title NOT LIKE '%林鳳%'
  AND v.title NOT LIKE '%吳楚帆%'
  AND v.title NOT LIKE '%石堅%'
  AND v.title NOT LIKE '%謝賢%'
  AND v.title NOT LIKE '%新馬師曾%'
  AND v.title NOT LIKE '%白雪仙%'
  AND s.jp_realized IS NOT NULL
  AND s.jp_realized != ''
  AND s.dur > 0
