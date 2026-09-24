WITH pre_means AS (
  SELECT w.video_id AS video_id, AVG(w.chars_per_sec) AS m
  FROM windows AS w
  INNER JOIN videos AS v ON v.video_id = w.video_id
  WHERE w.tier IN ('A', 'B')
    AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(v.upload_date, 1, 4) <= '2024'
  GROUP BY w.video_id
),
post_means AS (
  SELECT w.video_id AS video_id, AVG(w.chars_per_sec) AS m
  FROM windows AS w
  INNER JOIN videos AS v ON v.video_id = w.video_id
  WHERE w.tier IN ('A', 'B')
    AND substr(v.upload_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
    AND substr(v.upload_date, 1, 4) >= '2025'
  GROUP BY w.video_id
),
pre_ord AS (
  SELECT
    pre_means.m AS m,
    ROW_NUMBER() OVER (ORDER BY pre_means.m ASC, pre_means.video_id ASC) AS rn,
    COUNT(*) OVER () AS n_rows
  FROM pre_means
),
post_ord AS (
  SELECT
    post_means.m AS m,
    ROW_NUMBER() OVER (ORDER BY post_means.m ASC, post_means.video_id ASC) AS rn,
    COUNT(*) OVER () AS n_rows
  FROM post_means
)
SELECT CASE
    WHEN (SELECT COUNT(*) FROM pre_means) = 0 OR (SELECT COUNT(*) FROM post_means) = 0 THEN NULL
    WHEN (SELECT SUM(pre_means.m IS NULL) FROM pre_means) > 0 THEN NULL
    WHEN (SELECT SUM(post_means.m IS NULL) FROM post_means) > 0 THEN NULL
    ELSE (
      SELECT 1000.0 * AVG(post_ord.m)
      FROM post_ord
      WHERE post_ord.rn IN ((post_ord.n_rows + 1) / 2, (post_ord.n_rows + 2) / 2)
    ) - (
      SELECT 1000.0 * AVG(pre_ord.m)
      FROM pre_ord
      WHERE pre_ord.rn IN ((pre_ord.n_rows + 1) / 2, (pre_ord.n_rows + 2) / 2)
    )
  END
