WITH
marker(tok) AS (
  SELECT '粵劇'
  UNION ALL SELECT '任劍輝'
  UNION ALL SELECT '芳艷芬'
  UNION ALL SELECT '李小龍'
  UNION ALL SELECT '林鳳'
  UNION ALL SELECT '吳楚帆'
  UNION ALL SELECT '石堅'
  UNION ALL SELECT '謝賢'
  UNION ALL SELECT '新馬師曾'
  UNION ALL SELECT '白雪仙'
),
freq AS (
  SELECT char AS glyph, COUNT(*) AS occ
  FROM syllables
  GROUP BY char
),
common AS (
  SELECT glyph FROM freq WHERE occ >= 10
),
cell AS (
  SELECT syl.jp_match AS match_label
  FROM syllables AS syl
  INNER JOIN windows AS win ON win.uid = syl.uid
  INNER JOIN videos AS vid ON vid.video_id = syl.video_id
  INNER JOIN common AS com ON com.glyph = syl.char
  WHERE win.tier IN ('A', 'B')
    AND substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(vid.upload_date, 1, 4) >= '2025'
    AND vid.title IS NOT NULL
    AND vid.title <> ''
    AND NOT EXISTS (
      SELECT 1 FROM marker AS mk WHERE instr(vid.title, mk.tok) > 0
    )
    AND syl.jp_realized IS NOT NULL
    AND syl.jp_realized <> ''
    AND syl.dur > 0
)
SELECT COUNT(*) AS n_judgeable_other_common_post
FROM cell
