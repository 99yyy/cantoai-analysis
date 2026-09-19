WITH dated AS (
  SELECT
    video_id,
    substr(upload_date, 1, 4) AS yyyy
  FROM videos
)
SELECT COUNT(video_id)
FROM dated
WHERE yyyy GLOB '[0-9][0-9][0-9][0-9]'
  AND yyyy <= '2024'
