WITH pool_windows AS (
  SELECT
    w.video_id AS video_id,
    w.chars_per_sec AS cps,
    v.title AS title,
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
),
scores AS (
  SELECT
    pool_windows.video_id AS video_id,
    MIN(pool_windows.title) AS title,
    AVG(pool_windows.cps) AS score
  FROM pool_windows
  WHERE pool_windows.period IN ('pre', 'post')
  GROUP BY pool_windows.video_id
),
ranked AS (
  SELECT
    scores.video_id AS video_id,
    scores.score AS score,
    ROW_NUMBER() OVER (
      ORDER BY scores.score ASC, scores.title ASC, scores.video_id ASC
    ) AS rn,
    COUNT(*) OVER () AS g
  FROM scores
),
params AS (
  SELECT
    ranked.g AS g,
    CASE
      WHEN ranked.g < 2 THEN 0
      WHEN ranked.g < 20 THEN 1
      ELSE CAST(0.05 * ranked.g AS INTEGER)
    END AS k
  FROM ranked
  LIMIT 1
),
dropped AS (
  SELECT ranked.video_id AS video_id
  FROM ranked
  INNER JOIN params ON 1 = 1
  WHERE ranked.rn <= params.k
     OR ranked.rn > params.g - params.k
),
kept AS (
  SELECT pool_windows.cps AS cps, pool_windows.period AS period
  FROM pool_windows
  WHERE pool_windows.period IN ('pre', 'post')
    AND pool_windows.video_id NOT IN (SELECT dropped.video_id FROM dropped)
)
SELECT CASE
    WHEN (SELECT SUM(kept.cps IS NULL) FROM kept) > 0 THEN NULL
    WHEN (SELECT SUM(kept.period = 'pre') FROM kept) = 0 THEN NULL
    WHEN (SELECT SUM(kept.period = 'post') FROM kept) = 0 THEN NULL
    ELSE 1000.0 * (
      AVG(CASE WHEN kept.period = 'post' THEN kept.cps END)
      - AVG(CASE WHEN kept.period = 'pre' THEN kept.cps END)
    )
  END
FROM kept
