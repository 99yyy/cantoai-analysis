WITH occ AS (
  SELECT sy0.char AS glyph, COUNT(*) AS n_seen
  FROM syllables AS sy0
  GROUP BY sy0.char
)
SELECT CAST(SUM(CASE WHEN occ.n_seen < 10 THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
FROM windows AS win
JOIN syllables AS sy ON sy.uid = win.uid
JOIN videos AS vid ON vid.video_id = win.video_id
JOIN occ ON occ.glyph = sy.char
WHERE win.tier IN ('A', 'B')
  AND (substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]' AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) <= 2024)
