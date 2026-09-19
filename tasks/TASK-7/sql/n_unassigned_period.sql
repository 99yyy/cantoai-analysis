WITH clip AS (
  SELECT substr(upload_date, 1, 4) AS yyyy
  FROM videos
)
SELECT COUNT(*) AS n_unassigned_period
FROM clip
WHERE NOT (
    (yyyy GLOB '[0-9][0-9][0-9][0-9]' AND yyyy <= '2024')
    OR
    (yyyy GLOB '[0-9][0-9][0-9][0-9]' AND yyyy >= '2025')
  )
