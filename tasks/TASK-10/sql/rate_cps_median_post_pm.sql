WITH ordered AS (
  SELECT
    w.chars_per_sec AS cps,
    ROW_NUMBER() OVER (ORDER BY w.chars_per_sec ASC, w.uid ASC) AS rn,
    COUNT(*) OVER () AS n_rows
  FROM windows AS w
  INNER JOIN videos AS v ON v.video_id = w.video_id
  WHERE w.tier IN ('A', 'B')
    AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(v.upload_date, 1, 4) >= '2025'
)
SELECT CASE
    WHEN (SELECT SUM(ordered.cps IS NULL) FROM ordered) > 0 THEN NULL
    ELSE (
      SELECT 1000.0 * AVG(ordered.cps)
      FROM ordered
      WHERE ordered.rn IN ((ordered.n_rows + 1) / 2, (ordered.n_rows + 2) / 2)
    )
  END
