WITH year_clip AS (
  SELECT
    substr(upload_date, 1, 4) AS yyyy,
    CAST(substr(upload_date, 1, 4) AS INTEGER) AS year_n
  FROM videos
)
SELECT COALESCE(SUM(CASE
  WHEN yyyy GLOB '[0-9][0-9][0-9][0-9]' AND year_n >= 2025 THEN 1
  ELSE 0
END), 0) AS n_videos_post
FROM year_clip
