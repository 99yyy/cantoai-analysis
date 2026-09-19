WITH clip AS (
  SELECT substr(upload_date, 1, 4) AS yyyy
  FROM videos
)
SELECT COUNT(*) AS n_videos_post
FROM clip
WHERE yyyy GLOB '[0-9][0-9][0-9][0-9]'
  AND yyyy >= '2025'
