WITH vf9_period_clips AS (
  SELECT
    vf9_ab_clip.coverage AS cov,
    vf9_ab_clip.uid AS clip_uid
  FROM windows AS vf9_ab_clip
INNER JOIN videos AS vf9_channel_row
        ON vf9_channel_row.video_id = vf9_ab_clip.video_id
WHERE (vf9_ab_clip.tier = 'A' OR vf9_ab_clip.tier = 'B')
    AND ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) <= '2024')
),
vf9_ranked AS (
  SELECT
    cov,
    ROW_NUMBER() OVER (ORDER BY cov ASC, clip_uid ASC) AS rk,
    COUNT(*) OVER () AS n_clips
  FROM vf9_period_clips
)
SELECT 1000.0 * AVG(cov)
FROM vf9_ranked
WHERE rk IN (
  CASE WHEN n_clips % 2 = 1 THEN (n_clips + 1) / 2 ELSE n_clips / 2 END,
  CASE WHEN n_clips % 2 = 1 THEN (n_clips + 1) / 2 ELSE n_clips / 2 + 1 END
)
