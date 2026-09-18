SELECT COUNT(*) AS value
FROM syllables s
JOIN windows w ON s.uid = w.uid
JOIN videos v ON s.video_id = v.video_id
WHERE w.tier IN ('A', 'B')
  AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(v.upload_date, 1, 4) >= '2025'
  AND v.title IS NOT NULL
  AND v.title != ''
  AND (
    v.title LIKE '%粵劇%'
    OR v.title LIKE '%任劍輝%'
    OR v.title LIKE '%芳艷芬%'
    OR v.title LIKE '%李小龍%'
    OR v.title LIKE '%林鳳%'
    OR v.title LIKE '%吳楚帆%'
    OR v.title LIKE '%石堅%'
    OR v.title LIKE '%謝賢%'
    OR v.title LIKE '%新馬師曾%'
    OR v.title LIKE '%白雪仙%'
  )
  AND s.jp_realized IS NOT NULL
  AND s.jp_realized != ''
  AND s.dur > 0
