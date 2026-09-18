EXPORT_SQL = """
SELECT s.syl_id, s.uid, s.video_id, s.pos, s.char, s.start, s.end, s.dur, s.tier,
       s.jp_default, s.jp_ctx, s.jp_realized, s.jp_match
FROM syllables s
JOIN windows w ON w.uid = s.uid
WHERE w.tier IN ('A', 'B')
ORDER BY s.syl_id
"""
