WITH published_judgeable AS (
  SELECT
    lower(trim(s.jp_ctx)) AS tj_norm,
    lower(trim(py.hyp)) AS py_norm,
    lower(trim(gw.hyp)) AS g2pw_norm,
    lower(trim(s.jp_default)) AS default_norm,
    lower(trim(s.jp_realized)) AS realized_norm
  FROM syllables AS s
  INNER JOIN windows AS w
    ON s.uid = w.uid
  INNER JOIN pred_pycantonese AS py
    ON py.id = s.syl_id
  INNER JOIN pred_g2pw AS gw
    ON gw.id = s.syl_id
  WHERE w.tier IN ('A', 'B')
    AND length(trim(s.jp_realized)) > 0
    AND s.dur > 0
),
main_set AS (
  SELECT *
  FROM published_judgeable
  WHERE NOT (
    tj_norm = py_norm
    AND tj_norm = g2pw_norm
    AND py_norm = g2pw_norm
  )
)
SELECT SUM(CASE WHEN g2pw_norm = realized_norm THEN 1 ELSE 0 END) FROM main_set
