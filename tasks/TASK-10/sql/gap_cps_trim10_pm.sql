WITH labeled AS (
  SELECT
    w.video_id AS video_id,
    w.chars_per_sec AS cps,
    v.title AS title,
    CASE
      WHEN substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
       AND substr(v.upload_date, 1, 4) >= '2025' THEN 'post'
      WHEN substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
       AND substr(v.upload_date, 1, 4) <= '2024' THEN 'pre'
    END AS period
  FROM windows AS w
  JOIN videos AS v ON v.video_id = w.video_id
  WHERE w.tier IN ('A', 'B')
),
pool AS (
  SELECT
    video_id,
    MIN(title) AS title,
    AVG(cps) AS score
  FROM labeled
  WHERE period IN ('pre', 'post')
  GROUP BY video_id
),
ranked AS (
  SELECT
    video_id,
    score,
    title,
    ROW_NUMBER() OVER (ORDER BY score ASC, title ASC, video_id ASC) AS rn,
    COUNT(*) OVER () AS g
  FROM pool
),
params AS (
  SELECT
    g,
    CASE
      WHEN g < 2 THEN 0
      WHEN g < 20 THEN 1
      ELSE CAST(0.05 * g AS INTEGER)
    END AS k
  FROM ranked
  LIMIT 1
),
dropped AS (
  SELECT r.video_id AS video_id
  FROM ranked AS r
  JOIN params AS p ON 1 = 1
  WHERE r.rn <= p.k OR r.rn > p.g - p.k
),
remain AS (
  SELECT l.period AS period, l.cps AS cps
  FROM labeled AS l
  WHERE l.period IN ('pre', 'post')
    AND l.video_id NOT IN (SELECT video_id FROM dropped)
),
rates AS (
  SELECT period, 1000.0 * AVG(cps) AS rate_pm
  FROM remain
  GROUP BY period
)
SELECT
  (SELECT rate_pm FROM rates WHERE period = 'post')
  - (SELECT rate_pm FROM rates WHERE period = 'pre')
FROM windows
LIMIT 1
