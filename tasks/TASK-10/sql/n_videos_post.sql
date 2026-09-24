SELECT COUNT(*)
FROM videos
WHERE substr(upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(upload_date, 1, 4) >= '2025'
