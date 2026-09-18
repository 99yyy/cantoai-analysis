SELECT
  syllables.syl_id,
  syllables.uid,
  syllables.video_id,
  syllables.jp_match,
  syllables.jp_realized,
  syllables.jp_default,
  syllables.dur AS syllable_dur,
  windows.tier,
  windows.start AS t0_s,
  windows.end AS t1_s,
  windows.dur AS window_dur,
  windows.text_clean,
  videos.upload_date
FROM syllables
JOIN windows ON syllables.uid = windows.uid
JOIN videos ON windows.video_id = videos.video_id
WHERE windows.tier IN ('A', 'B')
  AND windows.text_clean != '如果覺得內容啱睇嘅subscribe';
