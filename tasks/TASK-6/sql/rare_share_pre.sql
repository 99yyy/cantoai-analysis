WITH
char_freq AS (
  SELECT s2.char AS ch, COUNT(*) AS n_char
  FROM syllables s2
  GROUP BY s2.char
),
rare_char AS (
  SELECT ch
  FROM char_freq
  WHERE n_char < 10
),
frame AS (
  SELECT s.char AS ch
  FROM syllables s
  JOIN windows w ON s.uid = w.uid
  JOIN videos v ON s.video_id = v.video_id
  WHERE w.tier IN ('A', 'B')
    AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
  AND substr(v.upload_date, 1, 4) <= '2024'
)
SELECT CAST(SUM(CASE WHEN rare_char.ch IS NOT NULL THEN 1 ELSE 0 END) AS REAL) / COUNT(*) AS value
FROM frame
LEFT JOIN rare_char ON frame.ch = rare_char.ch
