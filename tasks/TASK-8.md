# TASK-8：可判集上，tone/segment 是否撑起了发布后的不一致增量

status: closed
corpus_sha: 2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f
rung: Autopilot

## 目标

**TASK-7 已关闭。other×common 格上 pre−post 一致率差仍在，且整簇区间不含 0。TASK-6 审计 Finding 2：开放分析把剩余差距写进 tone/segment，但 TASK-6 的 `rate_*_pm` 分母是该期全部 A+B 音节，不是契约可判集上的划分，也不是对差距的贡献。本任务只测：在契约可判集上，不一致质量的 pre−post 上升是否集中在 `tone` 和/或 `segment`，而不是主要在 `diff`。**

不修任何东西，不试图把分数提高。不重做 TASK-6 / TASK-7 的整份数字表。本任务书的 `numbers` 块不写任何结果值。

## Prior Attempts

上一轮是 TASK-7（`tasks/TASK-7.md`，已 `closed`），产出在 `tasks/TASK-7/`；再上一轮是 TASK-6（`tasks/TASK-6.md`，已 `closed`），产出在 `tasks/TASK-6/`。本任务**不是** TASK-6 或 TASK-7 的分叉：要测的名字是新的，所以必须是新任务书 `tasks/TASK-8.md`。

TASK-6 钉死的期间差距 `gap_contract_pp` 约 9.05pp；film 组成解释约 1.91pp；剩余约 7.14pp。`rate_tone_*_pm` / `rate_segment_*_pm` / `rate_diff_*_pm` / `rate_none_*_pm` 的分母是该期**全部** A+B 音节（含不可判行）。审计 Finding 2：据此主张「剩余坐在 tone 和 segment 上」过强。

TASK-7 钉死 other×common 格 `gap_other_common_pp` 约 7.33pp；`video_id` 整簇 bootstrap 95% 区间不含 0；`ci_unreliable=0`。剩余下降在那一格，不在 film 组成或稀有字。以上全部以 `tasks/TASK-6/`、`tasks/TASK-7/`、`review/TASK-6/audit.md`、`review/TASK-7/audit.md` 为准；此处不另算、不另立主张，也不改那些文件里的数字。

本任务把 Finding 2 要的那张表变成要交的数字：契约可判集上 `tone` / `segment` / `diff` 的份额及其对不一致质量上升的贡献。

## 假说

数据：契约可判集（发布集 A+B，`jp_realized` 非空且 `dur > 0`）。比较：该类在可判集上的份额 `n_<class>_judgeable / n_judgeable` 的 pre−post 变化（声明名 `gap_share_<class>_pp`，class ∈ {tone, segment, diff}）。正值表示 post 可判集里该类更重，是不一致质量上升的一份。

否定「pre−post 不一致质量上升集中在 `tone` 和/或 `segment`，而不是主要在 `diff`」的结果：那两类对差距的贡献相对 `diff` 很小，或者可判类份额几乎不动而一致率仍因别的原因下降（例如可判行上出现未声明的 `jp_match` 取值，或下降发生在可判集之外的 none 消耗）。本任务书不把「很小」写成数值阈值、也不写任何类份额或贡献的预期值；`numbers` 块里的容差只约束重放和 worker/verifier 是否一致。区间、主次判断和「几乎不动」属于开放分析，不由 `output-check` 判。

## 输入

只读 `data/corpus_v2.sqlite`。读之前先算它的 sha256 并与 `README.md` 比对，不符就退出非零。不跑任何模型，不碰音频，不改数据库。不读、不改 TASK-6 或 TASK-7 的算路文件。

## 定义（两条算路必须用同一套）

- **发布集**：`windows.tier IN ('A','B')`。
- **期间**：`post` 是 `substr(videos.upload_date,1,4)` 为四位数字且 `>= '2025'`；`pre` 是四位数字且 `<= '2024'`。两个谓词都不满足的视频既不进 `pre` 也不进 `post`，其数量记为 `n_unassigned_period`。不得把任何一组定义成另一组的补集（契约第 18 条）。
- **可判**：按契约第 24 条。一个音节**可判**当且仅当 `jp_realized` 非空且 `dur > 0`。`n_judgeable_*` 是该期发布集上的可判音节数。可判行上 `jp_match` 为 NULL 则退出非零。
- **`jp_match` 枚举**：`exact_default`、`exact_alt`、`tone`、`segment`、`diff`、`none`。一致（`exact_default` 或 `exact_alt`）按第 24 条只在可判集内计；本任务不把一致率再声明一遍（不重做 `gap_contract_pp`）。
- **可判类计数**：`n_<class>_judgeable_*` 是**该期可判音节里** `jp_match` 恰好为该类的数量。`tone`、`segment`、`diff` 各是显式谓词，不是彼此的补集。三类都不匹配的可判行（`exact_default`、`exact_alt`，以及任何未声明取值）记为该类划分上的未分配，写入 `manifest.json`；一行同时匹配两类则退出非零。
- **可判类份额**：`n_<class>_judgeable_* / n_judgeable_*`。分母**只**是该期可判音节。TASK-6 的 `rate_*_pm` 分母是该期全部 A+B，本任务不得再用那个分母报类份额。
- **`none`**：`jp_match = 'none'` 与空的 `jp_realized` 是同一批行（TASK-6 口径）。可判定义要求 `jp_realized` 非空，所以可判集上 `none` **结构为 0**。禁止把可判条件下的 `none` 比率写进 `numbers`，装作它是可判份额。若要报全部 A+B 上的 `none` 消耗，写进 `manifest.json`，并标明分母是发布集全部音节、不是可判集。
- **贡献**：`gap_share_<class>_pp = 100 * (share_<class>_post - share_<class>_pre)`，单位百分点。这是该类在可判集上的份额变化，不是 TASK-6 的千分比差，也不是把 `gap_contract_pp` 再算一遍。列出每一类自己的 pre 份额、post 份额和这一贡献，读者才能重算。
- **计数**：契约第 24 条要求每个报告的一致率都附上 `n_total`、`n_match`、`n_judgeable`、`n_empty_realized`、`n_dur_le_0` 与后两者的交集。本任务不声明一致率，但开放分析若提到一致率下降，这些计数仍写进 `manifest.json`。`dur > 0` 是可判定义的一部分：契约第 25 条要求声明被它丢掉的行，那就是各期的 `n_dur_le_0`。两项剔除有交集，所以 `n_judgeable` 不等于 `n_total` 减那两个剔除数。
- **总体**：这 567 条视频来自同一个 YouTube 频道。聚类停在 `video_id`。总体写成「这个频道的 567 条视频」，不要写成「粤语」或「Cantonese」。
- **pp** 是百分点。

## 要交的数字

下面是这个任务必须交出的全部数字。**这里只有名字和容差，没有值**——值由 worker 和 verifier 各自从语料算出，两条算路必须在容差内一致。

```numbers
# name                           tol
n_videos_pre                     0
n_videos_post                    0
n_unassigned_period              0
n_judgeable_pre                  0
n_judgeable_post                 0
n_tone_judgeable_pre             0
n_tone_judgeable_post            0
n_segment_judgeable_pre          0
n_segment_judgeable_post         0
n_diff_judgeable_pre             0
n_diff_judgeable_post            0
gap_share_tone_pp                0.05
gap_share_segment_pp             0.05
gap_share_diff_pp                0.05
```

各自的算法：

- `n_videos_pre` / `n_videos_post` / `n_unassigned_period` 与 TASK-6 / TASK-7 同一套期间谓词，数的是视频。`n_unassigned_period` 今天应当是 0；容差是 0，所以将来语料一变就会红。这三个必须走 SQL，以便下面期间恒等式在该文件上被计。
- `n_judgeable_*` 是该期发布集上的契约可判音节数（与 TASK-6 的 `n_judgeable_pre` / `n_judgeable_post` 同一口径，本任务独立重算，不引用 TASK-6 的输出文件）。
- `n_<class>_judgeable_*` 是**同一批可判音节里** `jp_match` 恰好为 `tone` / `segment` / `diff` 的数量，不是该期全部 A+B 里该类的数量。
- `gap_share_<class>_pp` 是 `100 * (n_<class>_judgeable_post / n_judgeable_post - n_<class>_judgeable_pre / n_judgeable_pre)`，单位百分点。容差与 TASK-6 的 `gap_contract_pp`、TASK-7 的 `gap_other_common_pp` 相同。
- 不声明 TASK-6 / TASK-7 的其余名字。不把 `gap_contract_pp` 或 `gap_other_common_pp` 再算一遍。不声明可判条件下的 `none` 计数或份额。

## 怎么交这 14 个数字

两个 agent 交的是**同一种文件**，形状一样，都不含任何判定字段：

```
worker    tasks/TASK-8/results.json
verifier  tasks/TASK-8/mine.json

[{"name": …, "value": <数>, "n": <整数>, "query": "…"}]
```

谁都不写 `match`，也不写 `abs_diff`。比对由 `output-check` 做。本 PR 只开任务书：不要在这一步提交 `results.json`、`mine.json`、`RESULT.json` 或 `launches.json`。

`query` 是这个数字的算路，`output-check` 会**照着它把每个数字重新跑一遍**，跑出来的和你写下的不一致就红。只有两种形式：

- **`tasks/TASK-8/sql/<名>.sql`**（worker）或 **`tasks/TASK-8/mine_sql/<名>.sql`**（verifier）：一个文件一条语句，`SELECT` 或 `WITH` 开头，返回**恰好一行一列**，那一格就是这个数字。
- **`derived:<表达式>`**：只能用这 14 个名字里的其他名字、数字、`+ - * /` 和括号。例如
  `derived:100 * (n_tone_judgeable_post / n_judgeable_post - n_tone_judgeable_pre / n_judgeable_pre)`。
  重放时代进去的是**重放出来的**输入值，不是你写下的值。

两条约束：一个 `.sql` 文件只能支撑一个数字；worker 与 verifier 不得指向同一个 `.sql` 文件，所以两个目录分开。`derived:` 两边写成一样没问题，它的每个输入都各自被重放过。开工前先定下哪些走 SQL、哪些走 `derived:`。`n_videos_*` 与 `n_unassigned_period` 必须走 SQL。两条算路里有一条把三个 `gap_share_*_pp` 写成上面那种 `derived:` 式子最好，另一条直接查，这样恒等式本身也被验了一遍。

## `n` 是什么

`n` 是这个数字**算在多少行语料上**。两条算路必须给出完全相同的 `n`，且每个 `n` 必须等于下面 ```n``` 块里声明的常数或 `derived:` 表达式（代入的是重放出来的值，不是 agent 写下的值）。只两边相等不够：两边一起抄 `1` 也会相等。

```n
# name                           n
n_videos_pre                     567
n_videos_post                    567
n_unassigned_period              567
n_judgeable_pre                  derived:n_judgeable_pre
n_judgeable_post                 derived:n_judgeable_post
n_tone_judgeable_pre             derived:n_judgeable_pre
n_tone_judgeable_post            derived:n_judgeable_post
n_segment_judgeable_pre          derived:n_judgeable_pre
n_segment_judgeable_post         derived:n_judgeable_post
n_diff_judgeable_pre             derived:n_judgeable_pre
n_diff_judgeable_post            derived:n_judgeable_post
gap_share_tone_pp                derived:n_judgeable_pre + n_judgeable_post
gap_share_segment_pp             derived:n_judgeable_pre + n_judgeable_post
gap_share_diff_pp                derived:n_judgeable_pre + n_judgeable_post
```

视频三个数的 `n` 是频道里全部 567 条视频（与 TASK-6 / TASK-7 相同）。可判音节这一族的 `n` 是该期可判音节数：三个类计数都落在与 `n_judgeable_*` 同一批行上。三个 `gap_share_*_pp` 跨 pre 与 post 两批可判行。

## 抽样框

下面 ```frame``` 块在出现 `videos_expected` 时激活恒等式
`n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected`
（容差 `videos_expected_tol`；未写则按 0）。没有这块、或没有 `videos_expected` 时，该条恒等式不运行。检查读的是这个字段，不得把 567 写进闸门脚本。期间定义见上文，与 TASK-6 / TASK-7 相同。

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
gap_share_tone_pp = 100 * (n_tone_judgeable_post / n_judgeable_post - n_tone_judgeable_pre / n_judgeable_pre)  0.05
gap_share_segment_pp = 100 * (n_segment_judgeable_post / n_judgeable_post - n_segment_judgeable_pre / n_judgeable_pre)  0.05
gap_share_diff_pp = 100 * (n_diff_judgeable_post / n_judgeable_post - n_diff_judgeable_pre / n_judgeable_pre)  0.05
```

## 还要交的东西（这部分不进 numbers 块）

列出每一类自己的 pre 份额、post 份额和 `gap_share_<class>_pp`，让读者能自己重算贡献。三类贡献加起来是可判集上 `tone+segment+diff` 份额的上升；它是否等于契约一致率下降，取决于可判行是否只落在已声明的枚举值上——未声明取值的行数记进 `manifest.json`。

`manifest.json` 记录每一步 `{step, rule, group, rows_before, rows_after}`，以及每个输入的 sha256、行数、列集和 git sha。发布集上被 `dur > 0` 丢掉的行、空 `jp_realized`、二者交集，以及全部 A+B 上的 `none` 消耗（若要报），都写在这里，不进 `numbers`。

若报告推断统计：按 `video_id` 整簇 bootstrap，`B >= 1000`，层 = 期间，层 `h` 的种子 `int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16)`，层种子两两不同。报每层 `G_h`。`G_h < 10` 的层发 `ci_unreliable=1`，该行 `conclusion=inconclusive` 并报实际可判视频数。比较在本任务书里已经声明（三个 `gap_share_*_pp`）：若报告 p 值，原始与 BH 校正一起报，`m = 3`。禁止写「not supported」。描述性行标 `descriptive=1`，不带推断统计。

**一句话结论**，只针对本任务写下的假说。主次（tone/segment 对 `diff`）是开放分析的判断，不由 `output-check` 判，也不要把「很小」的阈值写进 `numbers`。

这部分两条算路不会一致，也不要求一致——它由 Tom 和 `auditor` 判断，不由 `output-check` 判断。

## 已知的坑

`tier`、`coverage`、`chars_per_sec`、`aligned` 是被评估模型自己的产物（契约第 27 条）：本任务不按它们分层。

`dur > 0` 不得单独用作抽样框或分母而不声明丢掉的行（第 25 条）。`review_prior` 不得用来分层、过滤或加权（第 26 条）；它部分由 `jp_match` 决定。

TASK-6 的 `rate_*_pm` 不能当作本任务的类份额：分母不同。可判集上的 `none` 份额是 0，把它写进一致率分解会把空实现行混进可判分母。

按年切分时每格的视频数要一并报出来：2021 和 2023 的样本很小，别把小格当趋势。

## 分工

`worker` 与 `verifier` **同时启动，从同一个 `starting_ref`**。不是一个做完另一个再做：`output-check` 会检查引入你那个文件的 commit，它的树里不能有对方的文件，所以谁在对方合入之后才切分支，谁就红。

- `worker`，分支 `cursor/t8-worker-…`：写 `tasks/TASK-8/sql/`，需要时写 `src/`、`tests/`，交 `tasks/TASK-8/results.json` 与上面那部分开放分析。
- `verifier`，分支 `cursor/t8-verifier-…`：**不读 worker 的代码、对话、PR**，只读本文件和语料，用自己的 SQL 把这 14 个数字重算一遍，写 `tasks/TASK-8/mine_sql/`，交 `tasks/TASK-8/mine.json`。
- 不一致的行发回去重算。同一个输出文件最多被改三次——第一次加两次重试，`output-check` 数 commit。仍不一致就停，两套数字一起升级给 Tom。
- 两个都合入、`output-check` 报出 14 个全一致之后，把本文件的 `status:` 改成 `closed`，并写入一行 `corpus_sha:`，值为当时 `README.md` 里的语料 sha256。stamp 与当前 pin 不符或缺失时本任务是 STALE。改不动 `closed` 就说明还没齐。然后放 `auditor`，写 `review/TASK-8/audit.md` 与 `tasks/TASK-8/RESULT.json`。

两个 agent 都不能改本文件，但**必须**能写 `tasks/TASK-8/` 下面自己的产出。
