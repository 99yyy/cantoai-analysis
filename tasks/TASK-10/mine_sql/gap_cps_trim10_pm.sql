WITH pool AS (
  SELECT windows.video_id AS video_id,
         videos.title AS title,
         AVG(windows.chars_per_sec) AS score,
         SUM(CASE WHEN windows.chars_per_sec IS NULL THEN 1 ELSE 0 END) AS n_null
  FROM windows
  INNER JOIN videos ON videos.video_id = windows.video_id
  WHERE windows.tier IN ('A', 'B')
    AND substr(videos.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND (
      substr(videos.upload_date, 1, 4) <= '2024'
      OR substr(videos.upload_date, 1, 4) >= '2025'
    )
  GROUP BY windows.video_id, videos.title
),
sized AS (
  SELECT video_id,
         title,
         score,
         n_null,
         ROW_NUMBER() OVER (
           ORDER BY score ASC, title ASC, video_id ASC
         ) AS rn,
         COUNT(*) OVER () AS g
  FROM pool
),
bounds AS (
  SELECT g,
         CASE
           WHEN g < 2 THEN 0
           WHEN g < 20 THEN 1
           ELSE (g * 5) / 100
         END AS k
  FROM sized
  LIMIT 1
),
dropped AS (
  SELECT sized.video_id AS video_id
  FROM sized
  CROSS JOIN bounds
  WHERE sized.rn <= bounds.k
     OR sized.rn > bounds.g - bounds.k
),
kept AS (
  SELECT windows.chars_per_sec AS cps,
         substr(videos.upload_date, 1, 4) AS year
  FROM windows
  INNER JOIN videos ON videos.video_id = windows.video_id
  WHERE windows.tier IN ('A', 'B')
    AND windows.video_id NOT IN (SELECT video_id FROM dropped)
),
pre_mean AS (
  SELECT CASE
      WHEN SUM(CASE WHEN cps IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
      ELSE AVG(cps)
    END AS mean_cps
  FROM kept
  WHERE year GLOB '[0-9][0-9][0-9][0-9]'
    AND year <= '2024'
),
post_mean AS (
  SELECT CASE
      WHEN SUM(CASE WHEN cps IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
      ELSE AVG(cps)
    END AS mean_cps
  FROM kept
  WHERE year GLOB '[0-9][0-9][0-9][0-9]'
    AND year >= '2025'
)
SELECT CASE
    WHEN (SELECT SUM(n_null) FROM pool) > 0 THEN NULL
    ELSE 1000.0 * (post_mean.mean_cps - pre_mean.mean_cps)
  END
FROM pre_mean
CROSS JOIN post_mean
