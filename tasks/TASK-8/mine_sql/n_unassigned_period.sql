WITH channel_year AS (
  SELECT substr(upload_date, 1, 4) AS y4
  FROM videos
)
SELECT COUNT(*)
FROM channel_year
WHERE NOT (
  y4 GLOB '[0-9][0-9][0-9][0-9]'
  AND y4 + 0 <= 2024
)
AND NOT (
  y4 GLOB '[0-9][0-9][0-9][0-9]'
  AND y4 + 0 >= 2025
)
