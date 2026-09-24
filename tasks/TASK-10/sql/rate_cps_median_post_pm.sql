WITH ordered AS (
  SELECT
    w.chars_per_sec AS cps,
    ROW_NUMBER() OVER (ORDER BY w.chars_per_sec ASC, w.uid ASC) AS rn,
    COUNT(*) OVER () AS n
  FROM windows AS w
  JOIN videos AS v ON v.video_id = w.video_id
  WHERE w.tier IN ('A', 'B')
    AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(v.upload_date, 1, 4) >= '2025'
)
SELECT 1000.0 * AVG(cps)
FROM ordered
WHERE (n % 2 = 1 AND rn = (n + 1) / 2)
   OR (n % 2 = 0 AND (rn = n / 2 OR rn = n / 2 + 1))
