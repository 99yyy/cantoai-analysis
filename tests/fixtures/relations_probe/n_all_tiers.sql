SELECT COUNT(*)
FROM syllables s
JOIN windows w ON s.uid = w.uid
