WITH ordered AS (
  SELECT windows.chars_per_sec AS cps,
         ROW_NUMBER() OVER (
           ORDER BY windows.chars_per_sec ASC, windows.uid ASC
         ) AS rn,
         COUNT(*) OVER () AS n_rows
  FROM windows
  INNER JOIN videos ON videos.video_id = windows.video_id
  WHERE windows.tier IN ('A', 'B')
    AND windows.chars_per_sec IS NOT NULL
    AND substr(videos.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(videos.upload_date, 1, 4) >= '2025'
)
SELECT CASE
    WHEN (SELECT COUNT(*) FROM ordered) <> (
      SELECT COUNT(*)
      FROM windows
      INNER JOIN videos ON videos.video_id = windows.video_id
      WHERE windows.tier IN ('A', 'B')
        AND substr(videos.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
        AND substr(videos.upload_date, 1, 4) >= '2025'
    ) THEN NULL
    WHEN (SELECT n_rows FROM ordered LIMIT 1) % 2 = 1 THEN 1000.0 * (
      SELECT cps FROM ordered
      WHERE rn = ((SELECT n_rows FROM ordered LIMIT 1) + 1) / 2
    )
    ELSE 1000.0 * (
      (
        SELECT cps FROM ordered
        WHERE rn = (SELECT n_rows FROM ordered LIMIT 1) / 2
      ) + (
        SELECT cps FROM ordered
        WHERE rn = (SELECT n_rows FROM ordered LIMIT 1) / 2 + 1
      )
    ) / 2.0
  END
