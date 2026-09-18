SELECT 1000.0 * SUM(CASE WHEN sy.jp_match = 'none' THEN 1 ELSE 0 END) / COUNT(*)
FROM windows AS win
JOIN syllables AS sy ON sy.uid = win.uid
JOIN videos AS vid ON vid.video_id = win.video_id
WHERE win.tier IN ('A', 'B')
  AND (substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]' AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) >= 2025)
