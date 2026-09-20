WITH vf9_pre_vid AS (
  SELECT
    vf9_ab_clip.video_id AS vid,
    AVG(vf9_ab_clip.coverage) AS mean_cov
  FROM windows AS vf9_ab_clip
INNER JOIN videos AS vf9_channel_row
        ON vf9_channel_row.video_id = vf9_ab_clip.video_id
WHERE (vf9_ab_clip.tier = 'A' OR vf9_ab_clip.tier = 'B')
    AND ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) <= '2024')
  GROUP BY vf9_ab_clip.video_id
),
vf9_post_vid AS (
  SELECT
    vf9_ab_clip.video_id AS vid,
    AVG(vf9_ab_clip.coverage) AS mean_cov
  FROM windows AS vf9_ab_clip
INNER JOIN videos AS vf9_channel_row
        ON vf9_channel_row.video_id = vf9_ab_clip.video_id
WHERE (vf9_ab_clip.tier = 'A' OR vf9_ab_clip.tier = 'B')
    AND ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) >= '2025')
  GROUP BY vf9_ab_clip.video_id
),
vf9_pre_ranked AS (
  SELECT
    mean_cov,
    ROW_NUMBER() OVER (ORDER BY mean_cov ASC, vid ASC) AS rk,
    COUNT(*) OVER () AS n_vids
  FROM vf9_pre_vid
),
vf9_post_ranked AS (
  SELECT
    mean_cov,
    ROW_NUMBER() OVER (ORDER BY mean_cov ASC, vid ASC) AS rk,
    COUNT(*) OVER () AS n_vids
  FROM vf9_post_vid
),
vf9_pre_med AS (
  SELECT AVG(mean_cov) AS med_cov
  FROM vf9_pre_ranked
  WHERE rk IN (
    CASE WHEN n_vids % 2 = 1 THEN (n_vids + 1) / 2 ELSE n_vids / 2 END,
    CASE WHEN n_vids % 2 = 1 THEN (n_vids + 1) / 2 ELSE n_vids / 2 + 1 END
  )
),
vf9_post_med AS (
  SELECT AVG(mean_cov) AS med_cov
  FROM vf9_post_ranked
  WHERE rk IN (
    CASE WHEN n_vids % 2 = 1 THEN (n_vids + 1) / 2 ELSE n_vids / 2 END,
    CASE WHEN n_vids % 2 = 1 THEN (n_vids + 1) / 2 ELSE n_vids / 2 + 1 END
  )
)
SELECT 1000.0 * (SELECT med_cov FROM vf9_post_med)
     - 1000.0 * (SELECT med_cov FROM vf9_pre_med)
