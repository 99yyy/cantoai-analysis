WITH diff_row AS (
    SELECT
        CASE
            WHEN lower(trim(syllable.jp_ctx)) = lower(trim(syllable.jp_realized))
            THEN 1.0
            ELSE 0.0
        END AS ctx_hit,
        CASE
            WHEN lower(trim(syllable.jp_default)) = lower(trim(syllable.jp_realized))
            THEN 1.0
            ELSE 0.0
        END AS default_hit
    FROM syllables AS syllable
    INNER JOIN windows AS window
        ON window.uid = syllable.uid
    WHERE window.tier IN ('A', 'B')
      AND syllable.dur > 0
      AND length(trim(syllable.jp_realized)) > 0
      AND length(trim(coalesce(syllable.jp_ctx, ''))) > 0
      AND length(trim(coalesce(syllable.jp_default, ''))) > 0
      AND lower(trim(syllable.jp_ctx)) <> lower(trim(syllable.jp_default))
)
SELECT (1000.0 * SUM(ctx_hit) / COUNT(*)) - (1000.0 * SUM(default_hit) / COUNT(*))
FROM diff_row
