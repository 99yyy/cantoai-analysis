SELECT
  windows.uid,
  windows.video_id,
  windows.tier,
  windows.start AS t0_s,
  windows.end AS t1_s,
  windows.dur AS window_dur,
  windows.text_clean,
  videos.upload_date
FROM windows
JOIN videos ON windows.video_id = videos.video_id;
