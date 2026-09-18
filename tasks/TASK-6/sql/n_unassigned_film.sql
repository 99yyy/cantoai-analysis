SELECT COUNT(*) AS value
FROM videos v
WHERE v.title IS NULL OR v.title = ''
