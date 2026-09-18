FRAME_SQL = """
SELECT s.syl_id FROM syllables s
JOIN windows w ON w.uid = s.uid
WHERE w.tier IN ('A','B') AND IFNULL(s.dur,0)>0
"""
REPORTED_N = 7
