SELECT COUNT(*)
FROM windows AS win
INNER JOIN videos AS vid
  ON vid.video_id = win.video_id
WHERE win.tier IN ('A', 'B')
  AND win.flag_sing = 1
  AND substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) <= 2024
