SELECT 1000.0 * AVG(w.chars_per_sec)
FROM windows AS w
JOIN videos AS v ON v.video_id = w.video_id
WHERE w.tier IN ('A', 'B')
  AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(v.upload_date, 1, 4) <= '2024'
