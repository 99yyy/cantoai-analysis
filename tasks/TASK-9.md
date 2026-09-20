# TASK-9：语料 pin 不变，用现有列做发布前后内容/质量代理诊断

status: open
rung: Autopilot

## 目标

**TASK-8 已关闭。可判集上 tone / segment 份额差大于 diff。本任务不重测 `jp_match` 份额。只测：在现有语料列上，2025 年及之后的发布窗/视频是否呈现更差的弱质量代理，或更多唱/乐类 `flag_sing`，而这种代理移动有可能与 tone/segment 不一致上升同时出现。**

不修任何东西，不试图把分数提高。不重跑 VAD，不下载音频或模型，不改 `data/`，不发明 SNR / `singing_prob` / `content_type` 列。本任务书的 `numbers` 块不写任何结果值。

## Prior Attempts

上一轮是 TASK-8（`tasks/TASK-8.md`，已 `closed`，`tasks/TASK-8/RESULT.json`），再上一轮 TASK-7、TASK-6，产出分别在对应 `tasks/TASK-N/` 与 `review/TASK-N/`。本任务**不是**它们的分叉：要测的名字是新的，所以必须是新任务书 `tasks/TASK-9.md`。

TASK-6 钉死期间差距 `gap_contract_pp` 约 9.05pp；标题代理 film 的 Kitagawa 组成项约 1.91pp；剩余约 7.14pp。TASK-7 钉死 other×common 格 `gap_other_common_pp` 约 7.33pp；`video_id` 整簇 bootstrap 95% 区间不含 0。TASK-8 钉死可判集上 `gap_share_tone_pp` 约 3.58pp、`gap_share_segment_pp` 约 4.02pp，大于 `gap_share_diff_pp` 约 1.45pp。以上全部以那些任务的输出与 `RESULT` 为准；此处不另算，也不把 TASK-8 的 `jp_match` 份额再声明一遍。

本任务书已开题（窗加权代理差距）。质询员按 issue #89 Q2 打回：主指标是按行加权的组间差，缺同一差距按 cluster 取中位数的版本、以及去掉最极端 10% cluster 后的版本，与原值并排。本次只改任务书，不写结果。

## 假说

数据：发布集窗（`windows.tier IN ('A','B')`）及其所属视频，期间谓词与 TASK-8 相同。比较两项已声明的窗加权差距，并交它们的 Q2 稳健性版本：

- `gap_flag_sing_pm`：发布窗上 `flag_sing = 1` 的千分比，post − pre。正值表示 post 唱/乐类旗标更重。
- `gap_coverage_pm`：发布窗上 `coverage` 均值（×1000）的 post − pre。`coverage` 不是比例、常大于 1（见 `BACKGROUND.md`）；本任务**不**把更高或更低的 coverage 定义成「更好」。这一项只测均值是否移动。
- 同一差距的 cluster 中位数版：`gap_flag_sing_vidmed_pm`、`gap_coverage_vidmed_pm`（cluster = `video_id`）。
- 同一差距去掉最极端 10% cluster 后再按原窗加权定义重算：`gap_flag_sing_trim10_pm`、`gap_coverage_trim10_pm`。

开放分析必须把 **原值 / vidmed / trim10 三列并排**，`flag_sing` 与 `coverage` 各一张。质询 Q2（https://github.com/99yyy/cantoai-analysis/issues/89）：若三者中任两个的幅度相差超过 2 倍（绝对值之比 > 2；一者为 0 而另一者非 0 也算），或符号不一致，结论不得写成整体性变化——该行标 `conclusion=inconclusive`，或写明仅限于行加权（窗加权）口径。禁止写「not supported」。

否定「post 窗/视频呈现更差的弱质量代理或更多唱/乐类旗标」的结果：`flag_sing` 千分比在 post 并不更高，且 `coverage` 均值差距与 0 一致（开放分析里按下面的整簇区间判断；`numbers` 块的容差只约束重放，不是相对 0 的检验）；或者 Q2 的 2 倍/符号规则触发，因而不得主张整体性移动。本任务书不写这些差距、区间端点或 p 值的数值。

这**不是**对 `gap_contract_pp` 或 TASK-8 份额差的分解。代理差距在定义上不是那些差距的加数；它们的和也不等于总差距。禁止写「解释了」「撑起」「accounts for」「主要来自」。窗加权公式就是各自的 post − pre（见恒等式）；vidmed / trim10 是同一差距的另一种加权或样本，不是新的分解项。质询清单 Q3：https://github.com/99yyy/cantoai-analysis/issues/89

## 输入

只读 `data/corpus_v2.sqlite`。读之前先算它的 sha256 并与 `README.md` 比对，不符就退出非零。不跑任何模型，不碰音频，不改数据库。不读、不改 TASK-6 / TASK-7 / TASK-8 的算路文件。

## 定义（两条算路必须用同一套）

- **发布集**：`windows.tier IN ('A','B')`。任何关于发布集的统计都显式过滤 tier，并在 `manifest.json` 记录被这条规则丢掉的窗数（契约第 23 条）。`tier` 是被评估模型的产物（第 27 条）：丢掉的窗里有多少 `flag_sing = 1`，也记进 manifest，否则看不见已被档位规则排除的唱类旗标。
- **期间**：`post` 是 `substr(videos.upload_date,1,4)` 为四位数字且 `>= '2025'`；`pre` 是四位数字且 `<= '2024'`。两个谓词都不满足的视频既不进 `pre` 也不进 `post`，其数量记为 `n_unassigned_period`。不得把任何一组定义成另一组的补集（契约第 18 条）。
- **自然单位（质询 Q1）**：`upload_date` 的自然单位是日历年 `substr(upload_date,1,4)`。本任务用 pre/post 切，因此必须交一张按年切开的表（开放分析 + `manifest.json`，不进 `numbers`）：每格报 `n_videos`（即 `video_id` cluster 数）、该年发布窗数、以及该格的 `rate_flag_sing_pm` 与 `rate_coverage_pm`（与声明定义相同）。2021 与 2023 样本小，不得写成趋势。没有四位年份的视频计入 `n_unassigned_period`，并在年表里单列。
- **可判**（与 TASK-8 同一套，供开放分析若提到一致率时使用）：音节可判当且仅当 `jp_realized` 非空且 `dur > 0`。可判行上 `jp_match` 为 NULL 则退出非零。本任务声明的数字是**窗**上的代理，不用可判音节做分母，也不把 `dur > 0` 当作窗的抽样框。音节 `dur <= 0` 的剔除若在开放分析里出现，必须按第 25 条声明丢掉的行。
- **`flag_sing`**：`windows.flag_sing` 为整数。`n_flag_sing_*` 是该期发布窗里 `flag_sing` **恰好为 1** 的数量。`0` 与 `1` 以外的取值、或该期发布窗上 `flag_sing` 为 NULL，退出非零。这是模型旗标代理，不是内容判断，也不是标题关键词（质询 Q5）。开放分析必须写一句偏倚方向：把非唱窗标成唱，会把 `gap_flag_sing_pm` 往正（迎合假说）推；把唱窗漏标，会往负推。
- **`coverage`**：该期发布窗上 `windows.coverage` 的均值与中位数。NULL 则退出非零。不得 `fillna` / `COALESCE` / 哨兵。`rate_coverage_*_pm = 1000 * mean(coverage)`；`rate_coverage_median_*_pm = 1000 * median(coverage)`。中位数：将该期发布窗按 `(coverage ASC, uid ASC)` 排序；`n` 为奇数取第 `(n+1)/2` 个（1-based）的 `coverage`，偶数取第 `n/2` 与第 `n/2+1` 个的算术平均。`uid` 打破并列，使 permute 后仍确定。
- **窗计数**：`n_windows_*` 是该期发布窗数。该期无发布窗则退出非零，不得对空集取均值。
- **差距**：`gap_flag_sing_pm = rate_flag_sing_post_pm - rate_flag_sing_pre_pm`；`gap_coverage_pm = rate_coverage_post_pm - rate_coverage_pre_pm`。列出每一期自己的千分比，读者才能重算。pre 是基线期，不是第二套分组；这不是 DID，也不把两个差距互比当作要交的数字。若开放分析比较两个估计量的大小（质询 Q4），必须另交差值的整簇区间，以及一句「换成相对幅度结论是否翻转」；否则只分别相对 0 谈。
- **cluster 中位数（质询 Q2，cluster = `video_id`）**：每一期，只收该期至少有 1 个发布集窗的视频。该视频的 `rate_flag_sing_pm = 1000 * n_flag_sing_1 / n_windows`，分母是**该视频在该期的发布窗**。将这些 per-video 千分比按 `(rate ASC, video_id ASC)` 排序，奇数取第 `(n+1)/2` 个（1-based），偶数取第 `n/2` 与第 `n/2+1` 个的算术平均（与上面 coverage 窗中位数同一套奇偶规则）。该中位数就是开放分析里的 `rate_flag_sing_*_vidmed_pm`（已是 pm，不再乘 1000）。`gap_flag_sing_vidmed_pm = rate_flag_sing_post_vidmed_pm - rate_flag_sing_pre_vidmed_pm`。coverage：先对该视频该期发布窗取 `mean(coverage)`，再对 per-video 均值按 `(mean ASC, video_id ASC)` 取中位数，然后 `rate_coverage_*_vidmed_pm = 1000 *` 该中位数；`gap_coverage_vidmed_pm = rate_coverage_post_vidmed_pm - rate_coverage_pre_vidmed_pm`。四个期率不进 `numbers`，只进开放分析与 `manifest.json`，供重算两个已声明的 vidmed 差距。某一期没有任何「至少 1 个发布窗」的视频则退出非零。`video_id` 打破并列，使 permute 后仍确定。
- **去掉最极端 10% cluster（质询 Q2）**：池 = 在 pre **或** post 至少有 1 个发布集窗的全部 `video_id`，记其个数为 `G`。`k`：若 `G < 2`，则 `k = 0` 并在 manifest 写 `trim10_skipped=1`；若 `2 <= G < 20`，则 `k = 1`；若 `G >= 20`，则 `k` 为不大于 `0.05 * G` 的最大整数（对非负值即 `floor(0.05 * G)`，SQLite `CAST(0.05 * G AS INTEGER)`）。**flag_sing 修剪**：每个池内视频的得分 = 其池内发布窗上 `1000 * n_flag_sing_1 / n_windows`。按 `(score ASC, videos.title ASC, video_id ASC)` 排序，丢掉最低 `k` 个与最高 `k` 个视频（约 10% 两尾）。`title` 是记录列，排在 `video_id` 之前，避免并列时全序随主键拼写而变；cluster 仍是 `video_id`。剩下的窗 = 发布集窗且 `video_id` 不在丢掉集合里。只在剩下的窗上，按与 `gap_flag_sing_pm` **同一套**定义重算 post − pre（`1000 * n_flag_sing / n_windows` 的 post 减 pre），得到 `gap_flag_sing_trim10_pm`。**coverage 修剪独立**：得分 = 该视频池内发布窗的 `mean(coverage)`；同一套 `G`/`k`、同一套排序键、另一套丢掉集合。剩下的窗上按与 `gap_coverage_pm` 同一套定义重算，得到 `gap_coverage_trim10_pm`。两套丢掉集合不必相同，也不得互相定义成补集。某一期剩余发布窗为 0 则退出非零。剩余窗上 `flag_sing` 非 `{0,1}` 或 NULL、`coverage` 为 NULL，同样退出非零。manifest 记录 `G`、`k`、`trim10_skipped`、规则，以及 flag_sing / coverage 各自丢掉的视频数。
- **总体**：这 567 条视频来自同一个 YouTube 频道。聚类停在 `video_id`。总体写成「这个频道的 567 条视频」，不要写成「粤语」或「Cantonese」。
- **pp** 是百分点，**pm** 是千分之一。此处 `rate_*_pm` / `gap_*_pm` 是关系族要求的名字；coverage 的 pm 是「均值×1000」，不是比例的千分比。

## 要交的数字

下面是这个任务必须交出的全部数字。**这里只有名字和容差，没有值**——值由 worker 和 verifier 各自从语料算出，两条算路必须在容差内一致。

```numbers
# name                           tol
n_videos_pre                     0
n_videos_post                    0
n_unassigned_period              0
n_windows_pre                    0
n_windows_post                   0
n_flag_sing_pre                  0
n_flag_sing_post                 0
rate_flag_sing_pre_pm            0.5
rate_flag_sing_post_pm           0.5
gap_flag_sing_pm                 0.5
rate_coverage_pre_pm             0.5
rate_coverage_post_pm            0.5
gap_coverage_pm                  0.5
rate_coverage_median_pre_pm      0.5
rate_coverage_median_post_pm     0.5
gap_flag_sing_vidmed_pm          0.5
gap_coverage_vidmed_pm           0.5
gap_flag_sing_trim10_pm          0.5
gap_coverage_trim10_pm           0.5
```

各自的算法：

- `n_videos_pre` / `n_videos_post` / `n_unassigned_period` 与 TASK-8 同一套期间谓词，数的是视频。`n_unassigned_period` 的容差是 0；若它非 0，期间恒等式对不上就会红——pin 不会把它改写成 0。这三个必须走 SQL，以便期间恒等式在该文件上被计。
- `n_windows_*` 是该期发布窗数。
- `n_flag_sing_*` 是**同一批发布窗里** `flag_sing = 1` 的数量。
- `rate_flag_sing_*_pm` 是 `1000 * n_flag_sing_* / n_windows_*`。
- `gap_flag_sing_pm` 是 `rate_flag_sing_post_pm - rate_flag_sing_pre_pm`。
- `rate_coverage_*_pm` 是该期发布窗 `1000 * AVG(coverage)`。
- `gap_coverage_pm` 是 `rate_coverage_post_pm - rate_coverage_pre_pm`。
- `rate_coverage_median_*_pm` 是该期发布窗 `1000 * median(coverage)`（定义见上）。中位数是描述性稳健性对照：标 `descriptive=1`，不带 p 值，也不声明中位数差距。
- `gap_flag_sing_vidmed_pm` / `gap_coverage_vidmed_pm` 是同一差距按 `video_id` cluster 取中位数后的 post − pre（定义见上）。四个期率只进开放分析 / manifest。
- `gap_flag_sing_trim10_pm` / `gap_coverage_trim10_pm` 是丢掉最极端约 10% cluster 之后、在剩余发布窗上按原窗加权定义重算的 post − pre。两套修剪独立。
- 不声明 TASK-6 / TASK-7 / TASK-8 的其余名字。不把任何 `jp_match` 份额或一致率再算一遍。

## 怎么交这 19 个数字

两个 agent 交的是**同一种文件**，形状一样，都不含任何判定字段：

```
worker    tasks/TASK-9/results.json
verifier  tasks/TASK-9/mine.json

[{"name": …, "value": <数>, "n": <整数>, "query": "…"}]
```

谁都不写 `match`，也不写 `abs_diff`。比对由 `output-check` 做。本 PR 只开任务书：不要在这一步提交 `results.json`、`mine.json`、`RESULT.json` 或 `launches.json`。

`query` 是这个数字的算路，`output-check` 会**照着它把每个数字重新跑一遍**，跑出来的和你写下的不一致就红。只有两种形式：

- **`tasks/TASK-9/sql/<名>.sql`**（worker）或 **`tasks/TASK-9/mine_sql/<名>.sql`**（verifier）：一个文件一条语句，`SELECT` 或 `WITH` 开头，返回**恰好一行一列**，那一格就是这个数字。
- **`derived:<表达式>`**：只能用这 19 个名字里的其他名字、数字、`+ - * /` 和括号。例如
  `derived:1000 * (n_flag_sing_pre / n_windows_pre)`。
  重放时代进去的是**重放出来的**输入值，不是你写下的值。

两条约束：一个 `.sql` 文件只能支撑一个数字；worker 与 verifier 不得指向同一个 `.sql` 文件，所以两个目录分开。`derived:` 两边写成一样没问题，它的每个输入都各自被重放过。开工前先定下哪些走 SQL、哪些走 `derived:`。`n_videos_*`、`n_unassigned_period`、`n_windows_*`、`n_flag_sing_*` 必须走 SQL。两条算路里有一条把 `rate_flag_sing_*_pm` 与两个窗加权 `gap_flag_sing_pm` / `gap_coverage_pm` 写成上面那种 `derived:` 式子最好，另一条直接查，这样恒等式本身也被验了一遍。窗中位数没有整数加总式，两边都走 SQL。四个 Q2 稳健性差距不能从原 15 个名字算术出来，两边都走 SQL。

数字名必须落在 `relations.py` 的族里：`n_*` 在语料加倍后恰好翻倍；`rate_*_pm` 与 `gap_*` 落在原容差内。不要另起 `mean_` / `share_` 前缀。

## `n` 是什么

`n` 是这个数字**算在多少行语料上**。两条算路必须给出完全相同的 `n`，且每个 `n` 必须等于下面 ```n``` 块里声明的常数或 `derived:` 表达式（代入的是重放出来的值，不是 agent 写下的值）。只两边相等不够：两边一起抄 `1` 也会相等。

```n
# name                           n
n_videos_pre                     567
n_videos_post                    567
n_unassigned_period              567
n_windows_pre                    derived:n_windows_pre
n_windows_post                   derived:n_windows_post
n_flag_sing_pre                  derived:n_windows_pre
n_flag_sing_post                 derived:n_windows_post
rate_flag_sing_pre_pm            derived:n_windows_pre
rate_flag_sing_post_pm           derived:n_windows_post
gap_flag_sing_pm                 derived:n_windows_pre + n_windows_post
rate_coverage_pre_pm             derived:n_windows_pre
rate_coverage_post_pm            derived:n_windows_post
gap_coverage_pm                  derived:n_windows_pre + n_windows_post
rate_coverage_median_pre_pm      derived:n_windows_pre
rate_coverage_median_post_pm     derived:n_windows_post
gap_flag_sing_vidmed_pm          567
gap_coverage_vidmed_pm           567
gap_flag_sing_trim10_pm          derived:n_windows_pre + n_windows_post
gap_coverage_trim10_pm           derived:n_windows_pre + n_windows_post
```

视频三个数的 `n` 是频道里全部 567 条视频（与 TASK-8 相同）。两个 vidmed 差距也是视频级：`n` 同样是这 567 条；某一期没有发布窗的视频不进入该期中位数，进入的个数写进 manifest，不是声明数字。窗这一族的 `n` 是该期发布窗数：旗标计数、覆盖率均值/中位数都落在与 `n_windows_*` 同一批行上。窗加权 `gap_*_pm` 与两个 trim10 差距跨 pre 与 post 两批发布窗（trim10 是在同一框上再丢掉 cluster；丢掉步记入 manifest）。

## 抽样框

下面 ```frame``` 块在出现 `videos_expected` 时激活恒等式
`n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected`
（容差 `videos_expected_tol`；未写则按 0）。没有这块、或没有 `videos_expected` 时，该条恒等式不运行。检查读的是这个字段，不得把 567 写进闸门脚本。期间定义见上文，与 TASK-8 相同。

```frame
windows.tier IN ('A','B')
videos_expected 567
videos_expected_tol 0
windows_expected 4911
windows_expected_tol 0
syllables_expected 171867
syllables_expected_tol 0
published_expected 164693
published_expected_tol 0
```

## 恒等式

下面 ```identities``` 块每一行是 `<expr> = <expr>  <tol>`。`output-check` 用与 `derived:` 相同的 AST，代入**该文件重放出来的**值（不合并 worker 与 verifier 的字典）。`frame.<字段>` 绑定上面 ```frame``` 块的数值。一条恒等式**只在该文件里每一个出现的数字名都是 SQL 算路时才计**；任一名字是 `derived:` 就跳过。

```identities
n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected  0
rate_flag_sing_pre_pm = 1000 * n_flag_sing_pre / n_windows_pre  0.5
rate_flag_sing_post_pm = 1000 * n_flag_sing_post / n_windows_post  0.5
gap_flag_sing_pm = rate_flag_sing_post_pm - rate_flag_sing_pre_pm  0.5
gap_flag_sing_pm = 1000 * (n_flag_sing_post / n_windows_post - n_flag_sing_pre / n_windows_pre)  0.5
gap_coverage_pm = rate_coverage_post_pm - rate_coverage_pre_pm  0.5
```

四个 Q2 稳健性差距的期率不在 `numbers` 里，所以没有把它们写进本块的 post − pre 恒等式。双路 SQL 重放就是对它们的检查。

## 还要交的东西（这部分不进 numbers 块）

**按年切开的表（质询 Q1）**写入 `manifest.json` 与开放分析：自然单位 = 日历年。每格：`n_videos`、该年发布窗数、`rate_flag_sing_pm`、`rate_coverage_pm`。小格不得当趋势。描述性行标 `descriptive=1`。

**质询 Q2 并排表**：`flag_sing` 一行三列 `gap_flag_sing_pm` / `gap_flag_sing_vidmed_pm` / `gap_flag_sing_trim10_pm`；coverage 同样三列。旁边列出重算所需的期率：窗加权四个 `rate_*_pre/post_pm`（已声明）、四个 vidmed 期率、trim10 后两期窗加权期率。写明 Q2 句子：若任两个幅度相差超过 2 倍或符号不一致，结论不得写成整体性变化。

列出 `rate_flag_sing_pre_pm`、`rate_flag_sing_post_pm` 与 `gap_flag_sing_pm`，以及 coverage 均值的三个对应项，让读者能自己重算窗加权差距。写明：这些差距**是否在定义上必然等于**任何已关闭任务的总差距——答案是否；公式见上。不要写「解释了」或「撑起」。

`flag_sing` / 标题类代理的偏倚方向句（质询 Q5）必写。

可选描述性行（`descriptive=1`，不带推断统计）：`chars_per_sec` 均值、`videos.speech_s` / `n_windows`、窗 `dur`、`boundary_start` / `boundary_end` 取值份额。它们不是声明数字。

若报告推断统计：按 `video_id` 整簇 bootstrap，`B >= 1000`，层 = 期间，层 `h` 的种子 `int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16)`，层种子两两不同。报每层 `G_h`。`G_h < 10` 的层发 `ci_unreliable=1`，该行 `conclusion=inconclusive` 并报实际可判视频数。比较在本任务书里已经声明、需要 p 值的仍是两个窗加权差距（`gap_flag_sing_pm`、`gap_coverage_pm`）：若报告 p 值，原始与 BH 校正一起报，`m = 2`。窗中位数、vidmed、trim10 不进 `m`，不另报 p 值（可标 `descriptive=1`）。禁止写「not supported」。若比较两个差距谁更大，必须另交差值的区间（质询 Q4）。Q2 用三列点值判断能不能说整体性变化，不另占 `m`。

`manifest.json` 记录每一步 `{step, rule, group, rows_before, rows_after}`，以及每个输入的 sha256、行数、列集和 git sha。至少包括：非 A+B 窗的剔除、其中 `flag_sing = 1` 的数量、期间未分配视频、年表、每一期进入 vidmed 的视频数、trim10 的 `G` / `k` / `trim10_skipped` / 两套丢掉视频数与规则。

**一句话结论**，只针对本任务写下的假说。区间与 0 的关系、以及 Q2 三列是否触发 2 倍/符号规则，是开放分析的判断，不由 `output-check` 判。

这部分两条算路不会一致，也不要求一致——它由 Tom 和 `auditor` 判断，不由 `output-check` 判断。

## 已知的坑

`tier`、`coverage`、`chars_per_sec`、`aligned` 与 `flag_*` 是被评估模型自己的产物（契约第 27 条）。本任务把 `flag_sing` 与 `coverage` 当作**结果变量**，不按它们对 `jp_match` 分层；声明的千分比已经是未分层的发布窗数字。若再按它们或 `chars_per_sec` 分层，必须同时报未分层的那一版（即本任务已声明的两个 `rate_*_pre/post_pm`）。`aligned` 在本语料上不分开任何窗。

发布集过滤会先于 `flag_sing` 份额：档位规则已经拿掉的唱类窗，不会出现在声明的 `n_flag_sing_*` 里。只报 A+B 份额而不报剔除步，会把「档位已经丢掉唱窗」误读成「发布集没有唱」。

`dur > 0` 不得单独用作抽样框或分母而不声明丢掉的行（第 25 条）。本任务的窗分母不用音节 `dur`。`review_prior` 不得用来分层、过滤或加权（第 26 条）。

窗加权差距、cluster 中位数差距、trim10 差距不是同一个加权。三列并排若触发 Q2 规则，把窗加权写成「整体」就是质询不过。

trim10 的并列全序用 `videos.title` 再 `video_id`：得分并列在 `flag_sing` 上会很多；只按会被改写的主键排序，丢掉集合会随主键拼写而变，关系检查的加倍构造过不了。`title` 是记录列。不要为通过加倍去特判某个前缀。

将来的 SNR / `singing_prob` / `content_type` 不在本语料里。不要发明列。重建清单见 `investigations/post-2025-jyutping-drop/PLAN-corpus-columns.md`。

## 分工

`worker` 与 `verifier` **同时启动，从同一个 `starting_ref`**。不是一个做完另一个再做：`output-check` 会检查引入你那个文件的 commit，它的树里不能有对方的文件，所以谁在对方合入之后才切分支，谁就红。

- `worker`，分支 `cursor/t9-worker-…`：写 `tasks/TASK-9/sql/`，需要时写 `src/`、`tests/`，交 `tasks/TASK-9/results.json` 与上面那部分开放分析。
- `verifier`，分支 `cursor/t9-verifier-…`：**不读 worker 的代码、对话、PR**，只读本文件和语料，用自己的 SQL 把这 19 个数字重算一遍，写 `tasks/TASK-9/mine_sql/`，交 `tasks/TASK-9/mine.json`。
- 不一致的行发回去重算。同一个输出文件最多被改三次——第一次加两次重试，`output-check` 数 commit。仍不一致就停，两套数字一起升级给 Tom。
- 两个都合入、`output-check` 报出 19 个全一致之后，把本文件的 `status:` 改成 `closed`，并写入一行 `corpus_sha:`，值为当时 `README.md` 里的语料 sha256。stamp 与当前 pin 不符或缺失时本任务是 STALE。改不动 `closed` 就说明还没齐。然后放 `auditor`，写 `review/TASK-9/audit.md` 与 `tasks/TASK-9/RESULT.json`。

两个 agent 都不能改本文件，但**必须**能写 `tasks/TASK-9/` 下面自己的产出。
