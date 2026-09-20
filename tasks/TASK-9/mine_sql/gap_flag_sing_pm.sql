WITH vf9_tagged AS (
  SELECT
    vf9_ab_clip.flag_sing AS sing_flag,
    CASE
      WHEN ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) <= '2024') THEN 'pre'
      WHEN ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) >= '2025') THEN 'post'
      ELSE NULL
    END AS period_tag
  FROM windows AS vf9_ab_clip
INNER JOIN videos AS vf9_channel_row
        ON vf9_channel_row.video_id = vf9_ab_clip.video_id
WHERE (vf9_ab_clip.tier = 'A' OR vf9_ab_clip.tier = 'B')
)
SELECT
  (
    1000.0 * SUM(CASE WHEN period_tag = 'post' AND sing_flag = 1 THEN 1 ELSE 0 END)
    / SUM(CASE WHEN period_tag = 'post' THEN 1.0 ELSE 0.0 END)
  )
  -
  (
    1000.0 * SUM(CASE WHEN period_tag = 'pre' AND sing_flag = 1 THEN 1 ELSE 0 END)
    / SUM(CASE WHEN period_tag = 'pre' THEN 1.0 ELSE 0.0 END)
  )
FROM vf9_tagged
WHERE period_tag IS NOT NULL
