WITH pub AS (
  SELECT
    win.coverage AS coverage,
    win.uid AS uid
  FROM windows AS win
  INNER JOIN videos AS vid
    ON vid.video_id = win.video_id
  WHERE win.tier IN ('A', 'B')
    AND substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) <= 2024
),
ranked AS (
  SELECT
    pub.coverage AS coverage,
    ROW_NUMBER() OVER (ORDER BY pub.coverage ASC, pub.uid ASC) AS rn,
    COUNT(*) OVER () AS n
  FROM pub
)
SELECT 1000.0 * AVG(ranked.coverage)
FROM ranked
WHERE (
        ranked.n % 2 = 1
        AND ranked.rn = (ranked.n + 1) / 2
      )
   OR (
        ranked.n % 2 = 0
        AND (
          ranked.rn = ranked.n / 2
          OR ranked.rn = ranked.n / 2 + 1
        )
      )
