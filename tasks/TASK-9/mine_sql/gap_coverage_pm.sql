WITH vf9_tagged AS (
  SELECT
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
)
SELECT
  1000.0 * AVG(CASE WHEN period_tag = 'post' THEN cov END)
  -
  1000.0 * AVG(CASE WHEN period_tag = 'pre' THEN cov END)
FROM vf9_tagged
WHERE period_tag IS NOT NULL
