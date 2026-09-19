SELECT COUNT(*)
FROM syllables s
JOIN windows w ON s.uid = w.uid
JOIN videos v ON s.video_id = v.video_id
WHERE w.tier IN ('A', 'B')
  AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(v.upload_date, 1, 4) <= '2024'
  AND s.jp_realized IS NOT NULL
  AND s.jp_realized != ''
  AND s.dur > 0
;
