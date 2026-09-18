WITH
pre_g AS (
  SELECT
    SUM(CASE WHEN s.jp_match IN ('exact_default', 'exact_alt') THEN 1 ELSE 0 END) AS n_match,
    COUNT(*) AS n_den
  FROM syllables s
JOIN windows w ON s.uid = w.uid
JOIN videos v ON s.video_id = v.video_id
WHERE w.tier IN ('A', 'B')
    AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(v.upload_date, 1, 4) <= '2024'
    AND s.dur > 0
),
post_g AS (
  SELECT
    SUM(CASE WHEN s.jp_match IN ('exact_default', 'exact_alt') THEN 1 ELSE 0 END) AS n_match,
    COUNT(*) AS n_den
  FROM syllables s
JOIN windows w ON s.uid = w.uid
JOIN videos v ON s.video_id = v.video_id
WHERE w.tier IN ('A', 'B')
    AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(v.upload_date, 1, 4) >= '2025'
    AND s.dur > 0
)
SELECT 100.0 * (
  CAST(pre_g.n_match AS REAL) / pre_g.n_den
  - CAST(post_g.n_match AS REAL) / post_g.n_den
) AS value
FROM pre_g
JOIN post_g
