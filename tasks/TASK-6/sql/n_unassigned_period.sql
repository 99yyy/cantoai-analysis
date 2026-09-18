SELECT COUNT(*) AS value
FROM videos v
WHERE NOT (substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]')
