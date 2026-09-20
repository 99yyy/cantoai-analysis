WITH vf9_pre_vid AS (
  SELECT
    vf9_ab_clip.video_id AS vid,
    1000.0 * SUM(CASE WHEN vf9_ab_clip.flag_sing = 1 THEN 1 ELSE 0 END)
      / CAST(COUNT(*) AS REAL) AS rate_pm
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
    1000.0 * SUM(CASE WHEN vf9_ab_clip.flag_sing = 1 THEN 1 ELSE 0 END)
      / CAST(COUNT(*) AS REAL) AS rate_pm
  FROM windows AS vf9_ab_clip
INNER JOIN videos AS vf9_channel_row
        ON vf9_channel_row.video_id = vf9_ab_clip.video_id
WHERE (vf9_ab_clip.tier = 'A' OR vf9_ab_clip.tier = 'B')
    AND ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) >= '2025')
  GROUP BY vf9_ab_clip.video_id
),
vf9_pre_ranked AS (
  SELECT
    rate_pm,
    ROW_NUMBER() OVER (ORDER BY rate_pm ASC, vid ASC) AS rk,
    COUNT(*) OVER () AS n_vids
  FROM vf9_pre_vid
),
vf9_post_ranked AS (
  SELECT
    rate_pm,
    ROW_NUMBER() OVER (ORDER BY rate_pm ASC, vid ASC) AS rk,
    COUNT(*) OVER () AS n_vids
  FROM vf9_post_vid
),
vf9_pre_med AS (
  SELECT AVG(rate_pm) AS med_pm
  FROM vf9_pre_ranked
  WHERE rk IN (
    CASE WHEN n_vids % 2 = 1 THEN (n_vids + 1) / 2 ELSE n_vids / 2 END,
    CASE WHEN n_vids % 2 = 1 THEN (n_vids + 1) / 2 ELSE n_vids / 2 + 1 END
  )
),
vf9_post_med AS (
  SELECT AVG(rate_pm) AS med_pm
  FROM vf9_post_ranked
  WHERE rk IN (
    CASE WHEN n_vids % 2 = 1 THEN (n_vids + 1) / 2 ELSE n_vids / 2 END,
    CASE WHEN n_vids % 2 = 1 THEN (n_vids + 1) / 2 ELSE n_vids / 2 + 1 END
  )
)
SELECT (SELECT med_pm FROM vf9_post_med) - (SELECT med_pm FROM vf9_pre_med)
