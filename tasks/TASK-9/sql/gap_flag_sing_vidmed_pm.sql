WITH labeled AS (
  SELECT
    win.video_id AS video_id,
    win.flag_sing AS flag_sing,
    CASE
      WHEN substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
       AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) <= 2024
      THEN 'pre'
      WHEN substr(vid.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
       AND CAST(substr(vid.upload_date, 1, 4) AS INTEGER) >= 2025
      THEN 'post'
      ELSE 'unassigned'
    END AS period
  FROM windows AS win
  INNER JOIN videos AS vid
    ON vid.video_id = win.video_id
  WHERE win.tier IN ('A', 'B')
),
per_video AS (
  SELECT
    labeled.video_id AS video_id,
    labeled.period AS period,
    1000.0 * SUM(CASE WHEN labeled.flag_sing = 1 THEN 1 ELSE 0 END) / COUNT(*) AS rate_pm
  FROM labeled
  WHERE labeled.period IN ('pre', 'post')
  GROUP BY labeled.video_id, labeled.period
),
ranked AS (
  SELECT
    per_video.period AS period,
    per_video.rate_pm AS rate_pm,
    ROW_NUMBER() OVER (
      PARTITION BY per_video.period
      ORDER BY per_video.rate_pm ASC, per_video.video_id ASC
    ) AS rn,
    COUNT(*) OVER (PARTITION BY per_video.period) AS n
  FROM per_video
),
med AS (
  SELECT
    ranked.period AS period,
    AVG(ranked.rate_pm) AS med
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
  GROUP BY ranked.period
)
SELECT
  (SELECT med FROM med WHERE period = 'post')
  - (SELECT med FROM med WHERE period = 'pre')
