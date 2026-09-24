# TASK-11 开放分析

总体是这个频道的 567 条视频。聚类停在 `video_id`。发布集是 `windows.tier IN ('A','B')`，音节的 `tier` 与窗一致。比较前对 `jp_ctx`、`jp_default`、`jp_realized` 做 trim，再做 Unicode casefold。发布集上这三列都是 ASCII，casefold 与 `lower` 相同，SQL 用 `lower(trim(...))`。一致是规范化后整串相等，不用 `jp_match`。

主评测集是发布集可判定行里规范化后 `jp_ctx ≠ jp_default` 的行。可判定行上两列词典读音都非空。`jp_realized` 的训练标签来自词典侧，一致率可能被高估。

## 主评测集

| 名字 | 值 | n |
|---|---|---|
| n_diff_judgeable | 6022 | 6022 |
| n_same_judgeable | 133340 | 133340 |
| n_ctx_match | 3734 | 6022 |
| n_default_match | 965 | 6022 |
| agree_ctx_pm | 620.0597808037197 | 6022 |
| agree_default_pm | 160.24576552640318 | 6022 |
| gap_agree_pm | 459.81401527731657 | 6022 |

`agree_ctx_pm`、`agree_default_pm`、`gap_agree_pm` 都在这 6022 行上。`gap_agree_pm` 为正：这一子集上 `jp_ctx` 比 `jp_default` 更常与 `jp_realized` 整串一致。

## Q4 整簇区间

`gap_agree_ci` 不进 `numbers`。`master_seed` = 20260920，层 `diff` 的种子 `int(sha256("20260920:diff").hexdigest()[:8], 16)` = 4174636591。只有这一层，层种子没有第二值可撞。`B` = 2000。`G` = 550（主评测集上有行的视频数），`G_h` 同此数。`G` 不小于 10，`ci_unreliable` = 0。

有放回抽取这 550 个 `video_id`。一个簇被抽中 k 次，它在主评测集上的行就计入 k 次，然后在这批行上重算全局 `gap_agree_pm`。不是先在每个簇里算差值再对簇取均值或分位。

95% 百分位区间 [434.76390941377906, 486.35596541046806]，不含 0。`m` = 1。`p_raw` = 0，`p_BH` = 0：2000 次重算里差值都大于 0，负侧份额为 0，`p_raw = min(1, 2 * min(正侧份额, 负侧份额))`。

把差值换成相对 `agree_default_pm` 的幅度（`gap_agree_pm / agree_default_pm` = 2.8694300518134717）后，符号仍为正。同一套重采样下该幅度的 95% 百分位区间是 [2.5340972871842844, 3.266008399896326]，也不含 0。结论不翻转。

## Q5 错分方向

漏掉「本应不同却被标成相同」的行，主集会偏到更容易看见差的子集，`|gap_agree_pm|` 可能偏大。把噪声差纳进 ≠ 侧，`gap_agree_pm` 会被稀释。两侧规模是 `n_diff_judgeable` 与 `n_same_judgeable`。

## Q7

发布集可判定行上，规范化后 `jp_ctx ≠ jp_default` 为 6022，`=` 为 133340，与两个规模名相同。两边都不是单一取值，`q7_constant` = 0。

主评测集里 `char` 的顶频（descriptive）：話 545、呢 475、生 423、為 240、上 175、會 149、到 146、行 132、重 130、咁 120、下 118、名 111。主集 `char` 有 383 个不同值。

`n_cand` 在发布集可判定行上有 14 个取值：1 有 39303 行，2 有 44856，3 有 24947，4 有 19362，5 有 3653，6 有 1909，7 有 2782，8 有 602，9 有 234，10 有 3，11 有 1023，12 有 620，13 有 10，15 有 58。

「呢」用列 `next_char`。发布集可判定的「呢」有 750 行。`trim(next_char)` 为空的 28 行排除；没有行的 `next_char` 落在句末标点 `。！？!?．…` 里。非句末子集 722 行，其中 `jp_ctx` 整串一致 262 行，一致率 362.8808864265928（千分之一）。`descriptive` = 1。

`n_cand >= 2` 且发布集可判定：100059 行，`jp_ctx` 整串一致 79573 行，一致率 795.2607961302831（千分之一）。`descriptive` = 1。这两项不作头条。

## 契约第 24 条六计数

发布集：`n_total` 164693，`n_empty_realized` 2183，`n_dur_le_0` 23860，二者交集 712，`n_judgeable` 139362。可判定行上按本任务的整串一致谓词，`jp_ctx` 一致 112519，`jp_default` 一致 109750。可判定行上没有 NULL `jp_match`。

主评测集已经是可判定行，所以在这 6022 行上 `n_empty_realized`、`n_dur_le_0` 和交集都是 0，`n_judgeable` 等于 `n_total`。`n_match` 按 `jp_ctx` 与 `jp_realized` 整串相等，为 3734；`jp_default` 一侧为 965。

若先只取发布集上两列都非空且规范化后不等的行（7099），再套可判定：`n_empty_realized` 101，`n_dur_le_0` 1010，交集 34，可判定 6022。

## 结论

在这个频道的发布集可判定音节里，词典侧 `jp_ctx` 与 `jp_default` 不同的子集上，`jp_ctx` 相对 `jp_realized` 的一致率高于 `jp_default`，`gap_agree_pm` 的整簇区间在 0 的上方。
