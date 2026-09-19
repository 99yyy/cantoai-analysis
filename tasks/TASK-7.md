# TASK-7：other×common 格上，发布后一致率下降是否还在

status: open
rung: Autopilot

## 目标

**TASK-6 已关闭。标题代理 film 的 Kitagawa 组成只解释了 `gap_contract_pp` 的少数；剩余差距仍开着。本任务只测 TASK-6 `open_analysis.md` 里写下的那条剩余假说，而且只在 other×common 这一格上测。**

不修任何东西，不试图把分数提高。不重做 TASK-6 的整份数字表。本任务书的 `numbers` 块不写任何结果值。

## Prior Attempts

上一轮是 TASK-6（`tasks/TASK-6.md`，`status: closed`），产出在 `tasks/TASK-6/`。本任务**不是** TASK-6 的分叉：要测的名字是新的，所以必须是新任务书 `tasks/TASK-7.md`。

TASK-6 钉死的期间差距 `gap_contract_pp` 约 9.05pp；film 组成解释约 1.91pp（`explained_pp`）；剩余约 7.14pp（`residual_pp`）。`rare_share_*` 在 2025 年及之后更低，稀有字占比解释不了下降。`did_film_pp` 为负（film 格的下降小于 other 格）。以上全部以 `tasks/TASK-6/results.json`、`mine.json`、`open_analysis.md`、`decomposition.json` 为准；此处不另算、不另立主张。

TASK-6 开放分析写下的剩余假说（`tasks/TASK-6/open_analysis.md`）：在可判 A+B、other 标题代理、全库频次至少 10 的字上，pre−post 一致率差的 `video_id` 整簇 bootstrap 95% 区间若包含 0，则否定「剩余是普通非旧片用字上的库内不一致上升」。审计记录该比较没有跑。本任务把它变成要交的数字，以及同一条可证伪陈述。

## 假说

数据：契约可判集（发布集 A+B，`jp_realized` 非空且 `dur > 0`）∩ TASK-6 同一套标题代理的 `other` ∩ **common**（该字在 TASK-6 `rare_share_*` 所用的全库 `syllables` 表、全部 tier 上出现次数 ≥ 10）。比较：该格 `agreement(pre) − agreement(post)`，即声明名 `gap_other_common_pp`。否定「剩余差距是普通非旧片用字上的库内一致率下降」这条研究主张的结果：在本任务声明的推断程序下，该格差距与 0 一致——按 `video_id` 整簇 bootstrap（`B >= 1000`，层 = 期间）得到的 95% 区间包含 0，且没有 `ci_unreliable=1`。任一层 `G_h < 10` 时该行 `conclusion=inconclusive`，并报实际可判视频数；这不是否定。`numbers` 块里的容差只约束重放和 worker/verifier 是否一致，不是「相对 0」的检验。本任务书不写该格差距、区间端点或 p 值的数值。

## 输入

只读 `data/corpus_v2.sqlite`。读之前先算它的 sha256 并与 `README.md` 比对，不符就退出非零。不跑任何模型，不碰音频，不改数据库。不读、不改 TASK-6 的算路文件。

## 定义（两条算路必须用同一套）

- **发布集**：`windows.tier IN ('A','B')`。
- **期间**：`post` 是 `substr(videos.upload_date,1,4)` 为四位数字且 `>= '2025'`；`pre` 是四位数字且 `<= '2024'`。两个谓词都不满足的视频既不进 `pre` 也不进 `post`，其数量记为 `n_unassigned_period`。不得把任何一组定义成另一组的补集（契约第 18 条）。
- **一致率**：按契约第 24 条。一个音节**可判**当且仅当 `jp_realized` 非空且 `dur > 0`。`n_judgeable` 是可判音节数，`n_match` 是**可判音节里** `jp_match IN ('exact_default','exact_alt')` 的数量，一致率 = `n_match / n_judgeable`。分子必须和分母落在同一批行上，否则它不是一个比率。两项剔除**有交集**，所以 `n_judgeable` 不等于该格 `n_total` 减那两个剔除数——差的正是同时满足两项的行。可判行上 `jp_match` 为 NULL 则退出非零。用的词是一致率，不是准确率。
- **旧片组**：与 TASK-6 同一套标题代理。`film` 是 `title` 非空且包含以下任一者——`粵劇` `任劍輝` `芳艷芬` `李小龍` `林鳳` `吳楚帆` `石堅` `謝賢` `新馬師曾` `白雪仙`；`other` 是 `title` 非空且一个都不包含。`title` 为空的视频两组都不进。这是标题代理，不是内容判断，结论里要这么说。`other` 不是 `film` 的补集。
- **common**：该音节的 `char` 在**全库 `syllables` 表、全部 tier**（TASK-6 `rare_share_*` 所用的同一张表）上的出现次数 **≥ 10**。这是显式谓词，不是「非稀有字」。TASK-6 的稀有字谓词是同一张表上出现次数 **< 10**；本任务只测 common，不把 rare 定义成对照补集。
- **other×common 格**：发布集音节，同时满足该期、`other`、`common`。再交可判定义，得到本任务一致率的分母。空标题、film、非 common、不可判的行都不进这一格；pre 与 post 用同一套纳入/剔除规则，每条规则每组丢掉的行数记进 `manifest.json`（契约第 13、18 条）。
- **计数**：契约第 24 条要求每个报告的一致率都附上 `n_total`、`n_match`、`n_judgeable`、`n_empty_realized`、`n_dur_le_0` 与后两者的交集。本轮报告的两个一致率（other×common × pre/post）这些计数写进 `manifest.json`。其中该格的 `n_match_*` 与 `n_judgeable_*` 另外声明在下面的 `numbers` 块里由 `output-check` 钉死。`dur > 0` 是可判定义的一部分：契约第 25 条要求声明被它丢掉的行，那就是各格的 `n_dur_le_0`。
- **总体**：这 567 条视频来自同一个 YouTube 频道。聚类停在 `video_id`。总体写成「这个频道的 567 条视频」，不要写成「粤语」或「Cantonese」。
- **pp** 是百分点。

## 要交的数字

下面是这个任务必须交出的全部数字。**这里只有名字和容差，没有值**——值由 worker 和 verifier 各自从语料算出，两条算路必须在容差内一致。

```numbers
# name                           tol
n_videos_pre                     0
n_videos_post                    0
n_unassigned_period              0
n_judgeable_other_common_pre     0
n_judgeable_other_common_post    0
n_match_other_common_pre         0
n_match_other_common_post        0
agree_other_common_pre           0.0005
agree_other_common_post          0.0005
gap_other_common_pp              0.05
```

各自的算法：

- `n_videos_pre` / `n_videos_post` / `n_unassigned_period` 与 TASK-6 同一套期间谓词，数的是视频。`n_unassigned_period` 今天应当是 0；容差是 0，所以将来语料一变就会红。这三个必须走 SQL，以便下面期间恒等式在该文件上被计。
- `n_judgeable_other_common_*` 是 other×common 格里、该期、契约可判音节数。
- `n_match_other_common_*` 是**同一批可判音节里** `jp_match IN ('exact_default','exact_alt')` 的数量，不是该期全部匹配数，也不是 other 格里未交 common 的匹配数。
- `agree_other_common_*` 是该格该期的一致率：`n_match_other_common_* / n_judgeable_other_common_*`。分子分母都在可判集内。容差与 TASK-6 的 `agree_film_*` / `agree_other_*` 相同。
- `gap_other_common_pp` 是 `100 * (agree_other_common_pre - agree_other_common_post)`，单位百分点。容差与 TASK-6 的 `gap_contract_pp` 相同。
- 不声明 TASK-6 的其余名字。不把 `gap_contract_pp` 再算一遍。

## 怎么交这 10 个数字

两个 agent 交的是**同一种文件**，形状一样，都不含任何判定字段：

```
worker    tasks/TASK-7/results.json
verifier  tasks/TASK-7/mine.json

[{"name": …, "value": <数>, "n": <整数>, "query": "…"}]
```

谁都不写 `match`，也不写 `abs_diff`。比对由 `output-check` 做。本 PR 只开任务书：不要在这一步提交 `results.json`、`mine.json`、`RESULT.json` 或 `launches.json`。

`query` 是这个数字的算路，`output-check` 会**照着它把每个数字重新跑一遍**，跑出来的和你写下的不一致就红。只有两种形式：

- **`tasks/TASK-7/sql/<名>.sql`**（worker）或 **`tasks/TASK-7/mine_sql/<名>.sql`**（verifier）：一个文件一条语句，`SELECT` 或 `WITH` 开头，返回**恰好一行一列**，那一格就是这个数字。
- **`derived:<表达式>`**：只能用这 10 个名字里的其他名字、数字、`+ - * /` 和括号。例如
  `derived:100 * (agree_other_common_pre - agree_other_common_post)`。
  重放时代进去的是**重放出来的**输入值，不是你写下的值。

两条约束：一个 `.sql` 文件只能支撑一个数字；worker 与 verifier 不得指向同一个 `.sql` 文件，所以两个目录分开。`derived:` 两边写成一样没问题，它的每个输入都各自被重放过。开工前先定下哪些走 SQL、哪些走 `derived:`。`n_videos_*` 与 `n_unassigned_period` 必须走 SQL。两条算路里有一条把 `gap_other_common_pp` 写成上面那个 `derived:` 式子最好，另一条直接查，这样恒等式本身也被验了一遍。

## `n` 是什么

`n` 是这个数字**算在多少行语料上**。两条算路必须给出完全相同的 `n`，且每个 `n` 必须等于下面 ```n``` 块里声明的常数或 `derived:` 表达式（代入的是重放出来的值，不是 agent 写下的值）。只两边相等不够：两边一起抄 `1` 也会相等。

```n
# name                           n
n_videos_pre                     567
n_videos_post                    567
n_unassigned_period              567
n_judgeable_other_common_pre     derived:n_judgeable_other_common_pre
n_judgeable_other_common_post    derived:n_judgeable_other_common_post
n_match_other_common_pre         derived:n_judgeable_other_common_pre
n_match_other_common_post        derived:n_judgeable_other_common_post
agree_other_common_pre           derived:n_judgeable_other_common_pre
agree_other_common_post          derived:n_judgeable_other_common_post
gap_other_common_pp              derived:n_judgeable_other_common_pre + n_judgeable_other_common_post
```

视频三个数的 `n` 是频道里全部 567 条视频（与 TASK-6 相同）。other×common 一致率这一族的 `n` 是该格该期可判音节数：`n_match_*` 与 `agree_*` 都落在与 `n_judgeable_*` 同一批行上。

## 抽样框

下面 ```frame``` 块在出现 `videos_expected` 时激活恒等式
`n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected`
（容差 `videos_expected_tol`；未写则按 0）。没有这块、或没有 `videos_expected` 时，该条恒等式不运行。检查读的是这个字段，不得把 567 写进闸门脚本。期间定义见上文，与 TASK-6 相同。

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
gap_other_common_pp = 100 * (agree_other_common_pre - agree_other_common_post)  0.05
```

## 还要交的东西（这部分不进 numbers 块）

**该格差距的 `video_id` 整簇 bootstrap**：`B >= 1000`，层 = 期间（`pre` / `post`），层 `h` 的种子 `int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16)`，层种子两两不同。报每层 `G_h`（这个频道 567 条视频里该层的视频数）。`G_h < 10` 的层发 `ci_unreliable=1`，该行 `conclusion=inconclusive` 并报实际可判视频数。比较在本任务书里已经声明，`m = 1`：若报告 p 值，原始与 BH 校正一起报。禁止写「not supported」。

列出 `agree_other_common_pre` 与 `agree_other_common_post`，让读者能自己重算 `gap_other_common_pp`。

**一句话结论**，只针对本任务写下的假说。区间与 0 的关系是开放分析的判断，不由 `output-check` 判，也不要把区间写进 `numbers`。

这部分两条算路不会一致，也不要求一致——它由 Tom 和 `auditor` 判断，不由 `output-check` 判断。

## 已知的坑

`tier`、`coverage`、`chars_per_sec`、`aligned` 是被评估模型自己的产物（契约第 27 条）：本任务不按它们分层。film 是标题代理；common 是全库字频。

`dur > 0` 不得单独用作抽样框或分母而不声明丢掉的行（第 25 条）。`review_prior` 不得用来分层、过滤或加权（第 26 条）。

按年切分时每格的视频数要一并报出来：2021 和 2023 的样本很小，别把小格当趋势。

## 分工

`worker` 与 `verifier` **同时启动，从同一个 `starting_ref`**。不是一个做完另一个再做：`output-check` 会检查引入你那个文件的 commit，它的树里不能有对方的文件，所以谁在对方合入之后才切分支，谁就红。

- `worker`，分支 `cursor/t7-worker-…`：写 `tasks/TASK-7/sql/`，需要时写 `src/`、`tests/`，交 `tasks/TASK-7/results.json` 与上面那部分开放分析。
- `verifier`，分支 `cursor/t7-verifier-…`：**不读 worker 的代码、对话、PR**，只读本文件和语料，用自己的 SQL 把这 10 个数字重算一遍，写 `tasks/TASK-7/mine_sql/`，交 `tasks/TASK-7/mine.json`。
- 不一致的行发回去重算。同一个输出文件最多被改三次——第一次加两次重试，`output-check` 数 commit。仍不一致就停，两套数字一起升级给 Tom。
- 两个都合入、`output-check` 报出 10 个全一致之后，把本文件的 `status:` 改成 `closed`，并写入一行 `corpus_sha:`，值为当时 `README.md` 里的语料 sha256。stamp 与当前 pin 不符或缺失时本任务是 STALE。改不动 `closed` 就说明还没齐。然后放 `auditor`，写 `review/TASK-7/audit.md` 与 `tasks/TASK-7/RESULT.json`。

两个 agent 都不能改本文件，但**必须**能写 `tasks/TASK-7/` 下面自己的产出。
