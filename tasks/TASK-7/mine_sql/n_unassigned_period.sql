SELECT COUNT(*)
FROM videos
WHERE NOT (
        substr(upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
        AND substr(upload_date, 1, 4) <= '2024'
      )
  AND NOT (
        substr(upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
        AND substr(upload_date, 1, 4) >= '2025'
      )
