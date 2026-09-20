SELECT COUNT(*)
FROM videos AS vid
WHERE substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) <= 2024
