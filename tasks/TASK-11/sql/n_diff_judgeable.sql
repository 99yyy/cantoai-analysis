WITH published AS (
  SELECT lower(trim(s.jp_ctx)) AS jp_ctx,
         lower(trim(s.jp_default)) AS jp_default,
         lower(trim(s.jp_realized)) AS jp_realized,
         s.dur AS dur
  FROM syllables AS s
  JOIN windows AS w ON s.uid = w.uid
  WHERE w.tier IN ('A', 'B')
    AND s.tier = w.tier
),
judgeable AS (
  SELECT jp_ctx, jp_default, jp_realized, dur
  FROM published
  WHERE length(jp_realized) > 0
    AND dur > 0
)
SELECT COUNT(*)
FROM judgeable
WHERE jp_ctx != jp_default
