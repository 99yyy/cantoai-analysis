WITH frame AS (
    SELECT
        lower(trim(s.jp_ctx)) AS tj,
        lower(trim(py.hyp)) AS py,
        lower(trim(g.hyp)) AS g2,
        lower(trim(s.jp_realized)) AS realized
    FROM syllables AS s
    INNER JOIN windows AS w ON w.uid = s.uid
    INNER JOIN pred_pycantonese AS py ON py.id = s.syl_id
    INNER JOIN pred_g2pw AS g ON g.id = s.syl_id
    WHERE w.tier IN ('A', 'B')
      AND length(trim(coalesce(s.jp_realized, ''))) > 0
      AND s.dur > 0
)
SELECT count(*)
FROM frame
WHERE NOT (tj = py AND tj = g2 AND py = g2)
  AND py = realized
