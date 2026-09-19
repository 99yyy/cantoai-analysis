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
)
SELECT CAST(SUM(CASE WHEN rare_char.ch IS NOT NULL THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
FROM syllables s
JOIN windows w ON s.uid = w.uid
LEFT JOIN rare_char ON s.char = rare_char.ch
WHERE w.tier IN ('A', 'B')
