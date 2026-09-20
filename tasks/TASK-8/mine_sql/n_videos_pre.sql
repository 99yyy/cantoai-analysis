WITH channel_year AS (
  SELECT substr(upload_date, 1, 4) AS y4
  FROM videos
)
SELECT COUNT(*)
FROM channel_year
WHERE y4 GLOB '[0-9][0-9][0-9][0-9]'
  AND y4 + 0 <= 2024
