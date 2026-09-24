WITH pre_mean AS (
  SELECT CASE
      WHEN SUM(CASE WHEN windows.chars_per_sec IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
      ELSE AVG(windows.chars_per_sec)
    END AS mean_cps
  FROM windows
  INNER JOIN videos ON videos.video_id = windows.video_id
  WHERE windows.tier IN ('A', 'B')
    AND substr(videos.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(videos.upload_date, 1, 4) <= '2024'
),
post_mean AS (
  SELECT CASE
      WHEN SUM(CASE WHEN windows.chars_per_sec IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
      ELSE AVG(windows.chars_per_sec)
    END AS mean_cps
  FROM windows
  INNER JOIN videos ON videos.video_id = windows.video_id
  WHERE windows.tier IN ('A', 'B')
    AND substr(videos.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(videos.upload_date, 1, 4) >= '2025'
)
SELECT 1000.0 * (post_mean.mean_cps - pre_mean.mean_cps)
FROM pre_mean
CROSS JOIN post_mean
