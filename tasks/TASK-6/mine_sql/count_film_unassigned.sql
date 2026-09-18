SELECT COUNT(*)
FROM videos AS vid
WHERE vid.title IS NULL OR length(vid.title) = 0
