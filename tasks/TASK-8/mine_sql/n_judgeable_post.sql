WITH
post_year AS (
  SELECT video_id
  FROM videos
  WHERE substr(upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(upload_date, 1, 4) + 0 >= 2025
),
ab_clip AS (
  SELECT uid, video_id
  FROM windows
  WHERE tier = 'A' OR tier = 'B'
)
SELECT COUNT(*)
FROM syllables AS syl
JOIN ab_clip ON ab_clip.uid = syl.uid
JOIN post_year ON post_year.video_id = ab_clip.video_id
WHERE length(syl.jp_realized) > 0
  AND syl.dur > 0
