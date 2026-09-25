WITH published_syllable AS (
    SELECT
        syllable.syl_id AS syl_id,
        lower(trim(syllable.jp_ctx)) AS ctx_fold,
        lower(trim(syllable.jp_default)) AS default_fold
    FROM syllables AS syllable
    INNER JOIN windows AS window
        ON window.uid = syllable.uid
    WHERE window.tier IN ('A', 'B')
      AND syllable.dur > 0
      AND length(trim(syllable.jp_realized)) > 0
      AND syllable.jp_ctx IS NOT NULL
      AND length(trim(syllable.jp_ctx)) > 0
      AND syllable.jp_default IS NOT NULL
      AND length(trim(syllable.jp_default)) > 0
)
SELECT COUNT(*)
FROM published_syllable
WHERE ctx_fold = default_fold
