# TASK-10：发布窗 chars_per_sec 是否在 2025 及之后比之前更快

status: open
rung: Autopilot

## 目标

在发布集窗上测量 `windows.chars_per_sec` 的期际差距：post（上传年 ≥2025）减 pre（上传年 ≤2024）。假说是 `gap_cps_pm > 0`（post 更快）。不修任何东西，不重跑模型，不改 `data/`。本任务书的 `numbers` 块不写任何结果值。

## Prior Attempts

上一轮是 TASK-9（`tasks/TASK-9.md`，已 `closed`），再上 TASK-8/7/6。本任务不是它们的分叉：测量对象是新的（语速代理 `chars_per_sec`），因此是新任务书 `tasks/TASK-10.md`。期间谓词、发布集、Q2 稳健性形态与 TASK-9 对齐，便于对照；不重报 TASK-6–9 的一致率或代理差距。

提案经 Tom「可以」采纳；质询员对提案打回 Q7（缺 `chars_per_sec` 在框内 pre/post 取值分布），已并入下文开放分析，不另等一轮。

## 假说

数据：发布集窗（`windows.tier IN ('A','B')`）及其所属视频。比较窗加权的 `chars_per_sec` 均值差距，并交 Q2 稳健性版本：

- `gap_cps_pm`：`1000 * mean(chars_per_sec)` 的 post − pre。正值表示 post 更快。
- `gap_cps_vidmed_pm`：同一差距按 `video_id` cluster 取中位数后的 post − pre。
- `gap_cps_trim10_pm`：去掉最极端约 10% cluster 后、在剩余发布窗上按原窗加权定义重算的 post − pre。

开放分析必须把 **原值 / vidmed / trim10 三列并排**。质询 Q2：若三者中任两个的幅度相差超过 2 倍（绝对值之比 > 2；一者为 0 而另一者非 0 也算），或符号不一致，结论不得写成整体性变快——该行标 `conclusion=inconclusive`，或写明仅限于行加权（窗加权）口径。禁止写「not supported」。

否定假说的结果：`gap_cps_pm` 与 0 一致（开放分析里按整簇区间判断；`numbers` 容差只约束重放），或 Q2 的 2 倍/符号规则触发。本任务书不写这些差距、区间端点或 p 值的数值。

这不是对任何已关闭任务总差距的分解。禁止写「解释了」「撑起」「accounts for」「主要来自」。

## 输入

只读 `data/corpus_v2.sqlite`。读之前先算它的 sha256 并与 `README.md` 比对，不符就退出非零。不跑任何模型，不碰音频，不改数据库。不读、不改 TASK-6–9 的算路文件。

## 定义（两条算路必须用同一套）

- **发布集**：`windows.tier IN ('A','B')`。任何关于发布集的统计都显式过滤 tier，并在 `manifest.json` 记录被这条规则丢掉的窗数。
- **期间**：`post` 是 `substr(videos.upload_date,1,4)` 为四位数字且 `>= '2025'`；`pre` 是四位数字且 `<= '2024'`。两个谓词都不满足的视频既不进 `pre` 也不进 `post`，其数量记为 `n_unassigned_period`。不得把任何一组定义成另一组的补集。
- **自然单位（质询 Q1）**：`upload_date` 的自然单位是日历年 `substr(upload_date,1,4)`。本任务用 pre/post 切，因此必须交一张按年切开的表（开放分析 + `manifest.json`，不进 `numbers`）：每格报 `n_videos`、该年发布窗数、以及该格的 `rate_cps_pm`（与声明定义相同）。小年样本不得写成趋势。没有四位年份的视频计入 `n_unassigned_period`，并在年表里单列。
- **`chars_per_sec`**：该期发布窗上 `windows.chars_per_sec`。NULL 则退出非零。不得 `fillna` / `COALESCE` / 哨兵。`rate_cps_*_pm = 1000 * mean(chars_per_sec)`；`rate_cps_median_*_pm = 1000 * median(chars_per_sec)`。中位数：将该期发布窗按 `(chars_per_sec ASC, uid ASC)` 排序；`n` 为奇数取第 `(n+1)/2` 个（1-based），偶数取第 `n/2` 与第 `n/2+1` 个的算术平均。`uid` 打破并列。
- **窗计数**：`n_windows_*` 是该期发布窗数。该期无发布窗则退出非零。
- **差距**：`gap_cps_pm = rate_cps_post_pm - rate_cps_pre_pm`。列出每一期自己的千分比，读者才能重算。pre 是基线期；这不是 DID。
- **cluster 中位数（质询 Q2，cluster = `video_id`）**：每一期，只收该期至少有 1 个发布集窗的视频。该视频得分 = 其该期发布窗上 `mean(chars_per_sec)`。将这些 per-video 均值按 `(mean ASC, video_id ASC)` 排序，奇数取第 `(n+1)/2` 个，偶数取第 `n/2` 与第 `n/2+1` 个的算术平均。该中位数记为开放分析里的期率（已是 mean，再 `rate_cps_*_vidmed_pm = 1000 *` 该中位数）；`gap_cps_vidmed_pm = rate_cps_post_vidmed_pm - rate_cps_pre_vidmed_pm`。两个 vidmed 期率不进 `numbers`，只进开放分析与 `manifest.json`。某一期没有任何「至少 1 个发布窗」的视频则退出非零。
- **去掉最极端 10% cluster（质询 Q2）**：池 = 在 pre **或** post 至少有 1 个发布集窗的全部 `video_id`，记其个数为 `G`。`k`：若 `G < 2`，则 `k = 0` 并在 manifest 写 `trim10_skipped=1`；若 `2 <= G < 20`，则 `k = 1`；若 `G >= 20`，则 `k` 为不大于 `0.05 * G` 的最大整数。每个池内视频的得分 = 其池内发布窗上 `mean(chars_per_sec)`。按 `(score ASC, videos.title ASC, video_id ASC)` 排序，丢掉最低 `k` 个与最高 `k` 个视频。剩下的窗 = 发布集窗且 `video_id` 不在丢掉集合里。只在剩下的窗上，按与 `gap_cps_pm` **同一套**定义重算 post − pre，得到 `gap_cps_trim10_pm`。某一期剩余发布窗为 0 则退出非零。剩余窗上 `chars_per_sec` 为 NULL 同样退出非零。manifest 记录 `G`、`k`、`trim10_skipped`、规则与丢掉的视频数。
- **总体**：这批视频来自同一个 YouTube 频道。聚类停在 `video_id`。总体写成「这个频道的视频」，不要写成「粤语」或「Cantonese」。
- **pm** 是千分之一尺度：此处 `rate_cps_*_pm` / `gap_cps_*_pm` 是「均值×1000」的期际差，不是比例的千分比。

## 要交的数字

下面是这个任务必须交出的全部数字。**这里只有名字和容差，没有值**。

```numbers
# name                           tol
n_videos_pre                     0
n_videos_post                    0
n_unassigned_period              0
n_windows_pre                    0
n_windows_post                   0
rate_cps_pre_pm                  0.5
rate_cps_post_pm                 0.5
gap_cps_pm                       0.5
rate_cps_median_pre_pm           0.5
rate_cps_median_post_pm          0.5
gap_cps_vidmed_pm                0.5
gap_cps_trim10_pm                0.5
```

各自的算法：

- `n_videos_pre` / `n_videos_post` / `n_unassigned_period` 与 TASK-9 同一套期间谓词，数的是视频。必须走 SQL。
- `n_windows_*` 是该期发布窗数。
- `rate_cps_*_pm` 是该期发布窗 `1000 * AVG(chars_per_sec)`。
- `gap_cps_pm` 是 `rate_cps_post_pm - rate_cps_pre_pm`。
- `rate_cps_median_*_pm` 是该期发布窗 `1000 * median(chars_per_sec)`。中位数是描述性稳健性对照：标 `descriptive=1`，不带 p 值，也不声明中位数差距。
- `gap_cps_vidmed_pm` / `gap_cps_trim10_pm` 定义见上。vidmed 期率只进开放分析 / manifest。
- 不声明 TASK-6–9 的其余名字。

## 怎么交这 12 个数字

两个 agent 交的是**同一种文件**，形状一样，都不含任何判定字段：

```
worker    tasks/TASK-10/results.json
verifier  tasks/TASK-10/mine.json

[{"name": …, "value": <数>, "n": <整数>, "query": "…"}]
```

谁都不写 `match`，也不写 `abs_diff`。比对由 `output-check` 做。本 PR 只开任务书：不要在这一步提交 `results.json`、`mine.json`、`RESULT.json` 或 `launches.json`。

`query` 是这个数字的算路，`output-check` 会**照着它把每个数字重新跑一遍**，跑出来的和你写下的不一致就红。只有两种形式：

- **`tasks/TASK-10/sql/<名>.sql`**（worker）或 **`tasks/TASK-10/mine_sql/<名>.sql`**（verifier）：一个文件一条语句，`SELECT` 或 `WITH` 开头，返回**恰好一行一列**。
- **`derived:<表达式>`**：只能用这 12 个名字里的其他名字、数字、`+ - * /` 和括号。

两条约束：一个 `.sql` 文件只能支撑一个数字；worker 与 verifier 不得指向同一个 `.sql` 文件。`n_videos_*`、`n_unassigned_period`、`n_windows_*` 必须走 SQL。两条算路里有一条把 `rate_cps_*_pm` 与 `gap_cps_pm` 写成 `derived:` 最好，另一条直接查。窗中位数与两个 Q2 稳健性差距两边都走 SQL。

数字名必须落在 relations 族里：`n_*` 翻倍；`rate_*_pm` 与 `gap_*` 落在原容差内。不要另起 `mean_` / `share_` 前缀。

## `n` 是什么

```n
# name                           n
n_videos_pre                     567
n_videos_post                    567
n_unassigned_period              567
n_windows_pre                    derived:n_windows_pre
n_windows_post                   derived:n_windows_post
rate_cps_pre_pm                  derived:n_windows_pre
rate_cps_post_pm                 derived:n_windows_post
gap_cps_pm                       derived:n_windows_pre + n_windows_post
rate_cps_median_pre_pm           derived:n_windows_pre
rate_cps_median_post_pm          derived:n_windows_post
gap_cps_vidmed_pm                567
gap_cps_trim10_pm                derived:n_windows_pre + n_windows_post
```

视频三个数与 vidmed 的 `n` 是频道里全部 567 条视频（与 TASK-9 相同）。窗这一族的 `n` 是该期发布窗数。`gap_cps_pm` 与 trim10 跨 pre 与 post 两批发布窗。

## 抽样框

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

```identities
n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected  0
gap_cps_pm = rate_cps_post_pm - rate_cps_pre_pm  0.5
```

## 还要交的东西（这部分不进 numbers 块）

**按年切开的表（质询 Q1）**写入 `manifest.json` 与开放分析：自然单位 = 日历年。每格：`n_videos`、该年发布窗数、`rate_cps_pm`。小格不得当趋势。描述性行标 `descriptive=1`。

**质询 Q2 并排表**：一行三列 `gap_cps_pm` / `gap_cps_vidmed_pm` / `gap_cps_trim10_pm`。旁边列出重算所需的期率。写明 Q2 句子：若任两个幅度相差超过 2 倍或符号不一致，结论不得写成整体性变快。

列出 `rate_cps_pre_pm`、`rate_cps_post_pm` 与 `gap_cps_pm`，让读者能自己重算窗加权差距。写明：这些差距**是否在定义上必然等于**任何已关闭任务的总差距——答案是否；公式见上。不要写「解释了」或「撑起」。

**质询 Q7 框内取值分布**（必交，开放分析 + `manifest.json`，不进 `numbers`）：
1. **上传年**：抽样框内 pre / post 各组，`substr(upload_date,1,4)` 的取值分布（各年视频数与发布窗数）。
2. **`chars_per_sec`**：抽样框内 pre / post 各组，该列的取值分布。因连续量，至少交：非空窗数、distinct 取值个数、min、p25、median、p75、max；若某一组 distinct=1，必须显式写出该常数并标 `q7_constant=1`（Q7 不过情形）。不得用「作结果不另分层」豁免本项。

`chars_per_sec` / `tier` 是被评估模型的产物（契约第 27 条）。本任务把 `chars_per_sec` 当作**结果变量**，不按它分层；声明的率已经是未分层的发布窗数字。

若报告推断统计：按 `video_id` 整簇 bootstrap，`B >= 1000`，层 = 期间，层种子规则与 TASK-9 相同。报每层 `G_h`。`G_h < 10` 的层发 `ci_unreliable=1`。需要相对 0 谈的声明差距是 `gap_cps_pm`：若报告 p 值，原始与 BH 校正一起报，`m = 1`。中位数、vidmed、trim10 不进 `m`。区间端点不进 `numbers`。禁止写「not supported」。主结论只谈 gap 相对 0；若开放分析比较两个估计量大小，必须另交差值的整簇区间（质询 Q4）。

`manifest.json` 记录每一步 `{step, rule, group, rows_before, rows_after}`，以及每个输入的 sha256、行数、列集和 git sha。至少包括：非 A+B 窗的剔除、期间未分配视频、年表、Q7 两套分布、每一期进入 vidmed 的视频数、trim10 的 `G` / `k` / `trim10_skipped` / 丢掉视频数。

**一句话结论**，只针对本任务写下的假说。

## 已知的坑

`tier`、`chars_per_sec`、`coverage`、`aligned` 与 `flag_*` 是被评估模型自己的产物。窗加权、cluster 中位数、trim10 不是同一加权；Q2 三列触发规则时把窗加权写成「整体」即质询不过。trim10 并列全序用 `videos.title` 再 `video_id`。`review_prior` 不得用来分层、过滤或加权。

## 分工

`worker` 与 `verifier` **同时启动，从同一个 `starting_ref`**。

- `worker`，分支 `cursor/t10-worker-…`：写 `tasks/TASK-10/sql/`，交 `tasks/TASK-10/results.json` 与开放分析。
- `verifier`，分支 `cursor/t10-verifier-…`：不读 worker，写 `tasks/TASK-10/mine_sql/`，交 `tasks/TASK-10/mine.json`。
- 不一致发回重算；同一输出文件最多改三次。仍不一致就停。
- 两个都合入且全一致后，`auditor` 收口：`status: closed` + `corpus_sha:`，写 `review/TASK-10/audit.md` 与 `RESULT.json`。

两个 agent 都不能改本文件。

## 质询字段

Q1 分组边界: 自然单位=日历年；交按年切开表（每格 n_videos、发布窗数、rate_cps_pm）；主切 pre/post
Q2 加权单位: gap_cps_pm / gap_cps_vidmed_pm / gap_cps_trim10_pm 三名并排；2 倍或符号不一致不得写整体性变快
Q3 是否恒等式: 不适用 + 理由（不是份额分解；gap 就是 post−pre 定义，不写「解释了」）
Q4 差值区间: 主结论只谈 gap_cps_pm 相对 0；若比较两个估计量大小再交差值整簇区间；区间不进 numbers
Q5 代理错分方向: 不适用 + 理由（分组用 upload_date 记录列；chars_per_sec 是结果变量不是分层代理）
Q7 框内取值: 交 upload_date 年在框内 pre/post 分布，以及 chars_per_sec 在框内 pre/post 分布（见「还要交的东西」）
