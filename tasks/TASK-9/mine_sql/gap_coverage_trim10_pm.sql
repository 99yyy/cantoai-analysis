WITH vf9_pool_score AS (
  SELECT
    vf9_ab_clip.video_id AS vid,
    vf9_channel_row.title AS clip_title,
    AVG(vf9_ab_clip.coverage) AS cluster_score
  FROM windows AS vf9_ab_clip
INNER JOIN videos AS vf9_channel_row
        ON vf9_channel_row.video_id = vf9_ab_clip.video_id
WHERE (vf9_ab_clip.tier = 'A' OR vf9_ab_clip.tier = 'B')
    AND (((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) <= '2024') OR ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) >= '2025'))
  GROUP BY vf9_ab_clip.video_id, vf9_channel_row.title
),
vf9_ranked AS (
  SELECT
    vid,
    ROW_NUMBER() OVER (
      ORDER BY cluster_score ASC, clip_title ASC, vid ASC
    ) AS rk,
    COUNT(*) OVER () AS g_pool
  FROM vf9_pool_score
),
vf9_k AS (
  SELECT
    MAX(g_pool) AS g_pool,
    CASE
      WHEN MAX(g_pool) < 2 THEN 0
      WHEN MAX(g_pool) < 20 THEN 1
      ELSE CAST(0.05 * MAX(g_pool) AS INTEGER)
    END AS k_drop
  FROM vf9_ranked
),
vf9_dropped AS (
  SELECT vf9_ranked.vid AS vid
  FROM vf9_ranked
  INNER JOIN vf9_k ON 1 = 1
  WHERE vf9_ranked.rk <= vf9_k.k_drop
     OR vf9_ranked.rk > vf9_k.g_pool - vf9_k.k_drop
),
vf9_kept AS (
  SELECT
    vf9_ab_clip.flag_sing AS sing_flag,
    vf9_ab_clip.coverage AS cov,
    CASE
      WHEN ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) <= '2024') THEN 'pre'
      WHEN ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) >= '2025') THEN 'post'
      ELSE NULL
    END AS period_tag
  FROM windows AS vf9_ab_clip
INNER JOIN videos AS vf9_channel_row
        ON vf9_channel_row.video_id = vf9_ab_clip.video_id
WHERE (vf9_ab_clip.tier = 'A' OR vf9_ab_clip.tier = 'B')
    AND (((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) <= '2024') OR ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) >= '2025'))
    AND NOT EXISTS (
      SELECT 1
      FROM vf9_dropped
      WHERE vf9_dropped.vid = vf9_ab_clip.video_id
    )
)
SELECT
  1000.0 * AVG(CASE WHEN period_tag = 'post' THEN cov END)
  -
  1000.0 * AVG(CASE WHEN period_tag = 'pre' THEN cov END)
FROM vf9_kept
