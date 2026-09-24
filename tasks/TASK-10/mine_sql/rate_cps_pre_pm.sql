SELECT CASE
    WHEN SUM(CASE WHEN windows.chars_per_sec IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
    ELSE 1000.0 * AVG(windows.chars_per_sec)
  END
FROM windows
INNER JOIN videos ON videos.video_id = windows.video_id
WHERE windows.tier IN ('A', 'B')
  AND substr(videos.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(videos.upload_date, 1, 4) <= '2024'
