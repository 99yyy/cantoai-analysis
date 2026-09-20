WITH year_clip AS (
  SELECT
    video_id,
    substr(upload_date, 1, 4) AS yyyy,
    CAST(substr(upload_date, 1, 4) AS INTEGER) AS year_n
  FROM videos
),
published_windows AS (
  SELECT uid
  FROM windows
  WHERE tier IN ('A', 'B')
)
SELECT COUNT(*) AS n_segment_judgeable_post
FROM syllables AS syl
INNER JOIN published_windows AS pw ON pw.uid = syl.uid
INNER JOIN year_clip AS yc ON yc.video_id = syl.video_id
WHERE yc.yyyy GLOB '[0-9][0-9][0-9][0-9]'
  AND yc.year_n >= 2025
  AND syl.jp_realized IS NOT NULL
  AND syl.jp_realized <> ''
  AND syl.dur > 0
  AND syl.jp_match = 'segment'
