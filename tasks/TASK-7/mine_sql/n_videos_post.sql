SELECT SUM(
  CASE
    WHEN substr(upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
     AND substr(upload_date, 1, 4) >= '2025'
    THEN 1
    ELSE 0
  END
)
FROM videos
