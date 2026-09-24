WITH pre_means AS (
  SELECT windows.video_id AS video_id,
         AVG(windows.chars_per_sec) AS mean_cps,
         SUM(CASE WHEN windows.chars_per_sec IS NULL THEN 1 ELSE 0 END) AS n_null
  FROM windows
  INNER JOIN videos ON videos.video_id = windows.video_id
  WHERE windows.tier IN ('A', 'B')
    AND substr(videos.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(videos.upload_date, 1, 4) <= '2024'
  GROUP BY windows.video_id
),
post_means AS (
  SELECT windows.video_id AS video_id,
         AVG(windows.chars_per_sec) AS mean_cps,
         SUM(CASE WHEN windows.chars_per_sec IS NULL THEN 1 ELSE 0 END) AS n_null
  FROM windows
  INNER JOIN videos ON videos.video_id = windows.video_id
  WHERE windows.tier IN ('A', 'B')
    AND substr(videos.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(videos.upload_date, 1, 4) >= '2025'
  GROUP BY windows.video_id
),
pre_ordered AS (
  SELECT mean_cps,
         ROW_NUMBER() OVER (ORDER BY mean_cps ASC, video_id ASC) AS rn,
         COUNT(*) OVER () AS n_rows
  FROM pre_means
),
post_ordered AS (
  SELECT mean_cps,
         ROW_NUMBER() OVER (ORDER BY mean_cps ASC, video_id ASC) AS rn,
         COUNT(*) OVER () AS n_rows
  FROM post_means
),
pre_med AS (
  SELECT CASE
      WHEN (SELECT SUM(n_null) FROM pre_means) > 0 THEN NULL
      WHEN (SELECT n_rows FROM pre_ordered LIMIT 1) % 2 = 1 THEN (
        SELECT mean_cps FROM pre_ordered
        WHERE rn = ((SELECT n_rows FROM pre_ordered LIMIT 1) + 1) / 2
      )
      ELSE (
        (
          SELECT mean_cps FROM pre_ordered
          WHERE rn = (SELECT n_rows FROM pre_ordered LIMIT 1) / 2
        ) + (
          SELECT mean_cps FROM pre_ordered
          WHERE rn = (SELECT n_rows FROM pre_ordered LIMIT 1) / 2 + 1
        )
      ) / 2.0
    END AS med
),
post_med AS (
  SELECT CASE
      WHEN (SELECT SUM(n_null) FROM post_means) > 0 THEN NULL
      WHEN (SELECT n_rows FROM post_ordered LIMIT 1) % 2 = 1 THEN (
        SELECT mean_cps FROM post_ordered
        WHERE rn = ((SELECT n_rows FROM post_ordered LIMIT 1) + 1) / 2
      )
      ELSE (
        (
          SELECT mean_cps FROM post_ordered
          WHERE rn = (SELECT n_rows FROM post_ordered LIMIT 1) / 2
        ) + (
          SELECT mean_cps FROM post_ordered
          WHERE rn = (SELECT n_rows FROM post_ordered LIMIT 1) / 2 + 1
        )
      ) / 2.0
    END AS med
)
SELECT 1000.0 * (post_med.med - pre_med.med)
FROM pre_med
CROSS JOIN post_med
