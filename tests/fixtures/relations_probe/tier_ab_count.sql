SELECT COUNT(*)
FROM syllables s
JOIN windows w ON s.uid = w.uid
JOIN videos v ON s.video_id = v.video_id
WHERE w.tier IN ('A', 'B')
