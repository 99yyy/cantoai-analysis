SELECT COUNT(*)
FROM windows AS vf9_ab_clip
INNER JOIN videos AS vf9_channel_row
        ON vf9_channel_row.video_id = vf9_ab_clip.video_id
WHERE (vf9_ab_clip.tier = 'A' OR vf9_ab_clip.tier = 'B')
  AND ((length(substr(vf9_channel_row.upload_date, 1, 4)) = 4 AND substr(vf9_channel_row.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]') AND substr(vf9_channel_row.upload_date, 1, 4) >= '2025')
