WITH labeled AS (
  SELECT
    win.video_id AS video_id,
    vid.title AS title,
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
pool AS (
  SELECT
    labeled.video_id AS video_id,
    MAX(labeled.title) AS title,
    1000.0 * SUM(CASE WHEN labeled.flag_sing = 1 THEN 1 ELSE 0 END) / COUNT(*) AS score
  FROM labeled
  WHERE labeled.period IN ('pre', 'post')
  GROUP BY labeled.video_id
),
gk AS (
  SELECT
    COUNT(*) AS g,
    CASE
      WHEN COUNT(*) < 2 THEN 0
      WHEN COUNT(*) < 20 THEN 1
      ELSE CAST(0.05 * COUNT(*) AS INTEGER)
    END AS k
  FROM pool
),
ranked AS (
  SELECT
    pool.video_id AS video_id,
    ROW_NUMBER() OVER (
      ORDER BY pool.score ASC, pool.title ASC, pool.video_id ASC
    ) AS rn,
    gk.g AS g,
    gk.k AS k
  FROM pool
  CROSS JOIN gk
),
dropped AS (
  SELECT ranked.video_id AS video_id
  FROM ranked
  WHERE ranked.rn <= ranked.k
     OR ranked.rn > ranked.g - ranked.k
),
kept AS (
  SELECT labeled.period AS period, labeled.flag_sing AS flag_sing
  FROM labeled
  WHERE labeled.period IN ('pre', 'post')
    AND labeled.video_id NOT IN (SELECT dropped.video_id FROM dropped)
),
pre_s AS (
  SELECT
    COUNT(*) AS n_windows,
    SUM(CASE WHEN flag_sing = 1 THEN 1 ELSE 0 END) AS n_flag
  FROM kept
  WHERE period = 'pre'
),
post_s AS (
  SELECT
    COUNT(*) AS n_windows,
    SUM(CASE WHEN flag_sing = 1 THEN 1 ELSE 0 END) AS n_flag
  FROM kept
  WHERE period = 'post'
)
SELECT 1000.0 * (
  CAST(post_s.n_flag AS REAL) / post_s.n_windows
  - CAST(pre_s.n_flag AS REAL) / pre_s.n_windows
)
FROM pre_s
CROSS JOIN post_s
