WITH period_rate AS (
  SELECT
    CASE
      WHEN substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
       AND substr(v.upload_date, 1, 4) >= '2025' THEN 'post'
      WHEN substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
       AND substr(v.upload_date, 1, 4) <= '2024' THEN 'pre'
    END AS period,
    1000.0 * AVG(w.chars_per_sec) AS rate_pm
  FROM windows AS w
  JOIN videos AS v ON v.video_id = w.video_id
  WHERE w.tier IN ('A', 'B')
  GROUP BY period
)
SELECT
  (SELECT rate_pm FROM period_rate WHERE period = 'post')
  - (SELECT rate_pm FROM period_rate WHERE period = 'pre')
FROM windows
LIMIT 1
