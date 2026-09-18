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
  AND windows.text_clean != '如果覺得內容啱睇嘅subscribe'
  AND (
    syllables.jp_default LIKE 'ng%'
    OR syllables.jp_default LIKE 'gw%'
    OR syllables.jp_default LIKE 'kw%'
    OR (
      syllables.jp_default LIKE 'n%'
      AND syllables.jp_default NOT LIKE 'ng%'
    )
  );
