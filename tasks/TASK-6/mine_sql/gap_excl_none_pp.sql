WITH bucketed AS (
  SELECT
    CASE
      WHEN (substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]' AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) <= 2024) THEN 'pre'
      WHEN (substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]' AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) >= 2025) THEN 'post'
    END AS bucket,
    CASE WHEN sy.jp_match IN ('exact_default', 'exact_alt') THEN 1 ELSE 0 END AS is_hit
  FROM windows AS win
JOIN syllables AS sy ON sy.uid = win.uid
JOIN videos AS vid ON vid.video_id = win.video_id
  WHERE win.tier IN ('A', 'B')
  AND NOT (sy.jp_realized IS NULL OR length(sy.jp_realized) = 0)
),
agg AS (
  SELECT
    bucket,
    COUNT(*) AS n_row,
    SUM(is_hit) AS n_hit
  FROM bucketed
  WHERE bucket IS NOT NULL
  GROUP BY bucket
)
SELECT 100.0 * (
  (SELECT CAST(n_hit AS REAL) / n_row FROM agg WHERE bucket = 'pre')
  -
  (SELECT CAST(n_hit AS REAL) / n_row FROM agg WHERE bucket = 'post')
)
