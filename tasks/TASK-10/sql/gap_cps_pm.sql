WITH pub AS (
  SELECT
    w.chars_per_sec AS cps,
    CASE
      WHEN substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
        AND substr(v.upload_date, 1, 4) >= '2025' THEN 'post'
      WHEN substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
        AND substr(v.upload_date, 1, 4) <= '2024' THEN 'pre'
      ELSE 'unassigned'
    END AS period
  FROM windows AS w
  INNER JOIN videos AS v ON v.video_id = w.video_id
  WHERE w.tier IN ('A', 'B')
)
SELECT CASE
    WHEN SUM(pub.cps IS NULL) > 0 THEN NULL
    WHEN SUM(pub.period = 'pre') = 0 OR SUM(pub.period = 'post') = 0 THEN NULL
    ELSE 1000.0 * (
      AVG(CASE WHEN pub.period = 'post' THEN pub.cps END)
      - AVG(CASE WHEN pub.period = 'pre' THEN pub.cps END)
    )
  END
FROM pub
WHERE pub.period IN ('pre', 'post')
