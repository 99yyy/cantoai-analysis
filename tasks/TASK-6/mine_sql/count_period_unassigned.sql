SELECT COUNT(*)
FROM videos AS vid
WHERE NOT (substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]' AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) <= 2024) AND NOT (substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]' AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) >= 2025)
