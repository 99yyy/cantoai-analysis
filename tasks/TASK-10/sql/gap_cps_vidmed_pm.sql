WITH scored AS (
  SELECT
    w.video_id AS video_id,
    CASE
      WHEN substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
       AND substr(v.upload_date, 1, 4) >= '2025' THEN 'post'
      WHEN substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
       AND substr(v.upload_date, 1, 4) <= '2024' THEN 'pre'
    END AS period,
    AVG(w.chars_per_sec) AS mean_cps
  FROM windows AS w
  JOIN videos AS v ON v.video_id = w.video_id
  WHERE w.tier IN ('A', 'B')
  GROUP BY w.video_id, period
),
kept AS (
  SELECT period, video_id, mean_cps
  FROM scored
  WHERE period IN ('pre', 'post')
),
ordered AS (
  SELECT
    period,
    mean_cps,
    ROW_NUMBER() OVER (
      PARTITION BY period
      ORDER BY mean_cps ASC, video_id ASC
    ) AS rn,
    COUNT(*) OVER (PARTITION BY period) AS n
  FROM kept
),
med AS (
  SELECT period, AVG(mean_cps) AS med_cps
  FROM ordered
  WHERE (n % 2 = 1 AND rn = (n + 1) / 2)
     OR (n % 2 = 0 AND (rn = n / 2 OR rn = n / 2 + 1))
  GROUP BY period
)
SELECT
  1000.0 * (
    (SELECT med_cps FROM med WHERE period = 'post')
    - (SELECT med_cps FROM med WHERE period = 'pre')
  )
FROM videos
LIMIT 1
