# TASK-6：2025 年之后一致率下降，能被解释多少

status: closed
corpus_sha: 2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f

## 目标

**发布集在 2025 年及之后的一致率明显低于之前。把这个差距分解开，说清其中多少能由语料里已有的列解释，剩下多少不能。**

不修任何东西，不试图把分数提高。要回答的只有一件事：原因在哪一层。

## 输入

只读 `data/corpus_v2.sqlite`。读之前先算它的 sha256 并与 `README.md` 比对，不符就退出非零。不跑任何模型，不碰音频，不改数据库。

## 定义（两条算路必须用同一套）

- **发布集**：`windows.tier IN ('A','B')`。
- **期间**：`post` 是 `substr(videos.upload_date,1,4)` 为四位数字且 `>= '2025'`；`pre` 是四位数字且 `<= '2024'`。两个谓词都不满足的视频既不进 `pre` 也不进 `post`，其数量记为 `n_unassigned_period`。不得把任何一组定义成另一组的补集（契约第 18 条）。
- **一致率**：按契约第 24 条。一个音节**可判**当且仅当 `jp_realized` 非空且 `dur > 0`。`n_judgeable` 是可判音节数，`n_match` 是**可判音节里** `jp_match IN ('exact_default','exact_alt')` 的数量，一致率 = `n_match / n_judgeable`。分子必须和分母落在同一批行上，否则它不是一个比率。两项剔除**有交集**，所以 `n_judgeable` 不等于 `n_total` 减那两个剔除数——差的正是同时满足两项的行，单独声明为 `n_empty_and_zerodur_*`。
- **旧片组**：`film` 是 `title` 非空且包含以下任一者——`粵劇` `任劍輝` `芳艷芬` `李小龍` `林鳳` `吳楚帆` `石堅` `謝賢` `新馬師曾` `白雪仙`；`other` 是 `title` 非空且一个都不包含。`title` 为空的视频两组都不进，其**视频**数记为 `n_unassigned_film`。这些视频上的**可判音节**数另记为 `n_judgeable_unassigned_film_pre` / `n_judgeable_unassigned_film_post`（与 `n_judgeable_film_*` / `n_judgeable_other_*` 同一套可判定义）。`n_unassigned_film` 数的是视频，不能当作音节恒等式的第三项。这是标题代理，不是内容判断，结论里要这么说。
- **稀有字**：该字在**全库全部 tier** 出现少于 10 次。
- **计数**：契约第 24 条要求每个一致率都附上 `n_total`、`n_match`、`n_judgeable`、`n_empty_realized`、`n_dur_le_0` 与后两者的交集。本轮报告的每个一致率，这些计数都写进 `manifest.json`；其中 pre 与 post 两个总表的六个计数，以及 film/other 四格的 `n_judgeable`，另外声明在下面的 `numbers` 块里由 `output-check` 钉死。
- **pp** 是百分点，**pm** 是千分之一。

## 要交的数字

下面是这个任务必须交出的全部数字。**这里只有名字和容差，没有值**——值由 worker 和 verifier 各自从语料算出，两条算路必须在容差内一致。

```numbers
# name                     tol
n_videos_pre               0
n_videos_post              0
n_unassigned_period        0
n_unassigned_film          0
n_total_pre                0
n_total_post               0
n_match_pre                0
n_match_post               0
n_empty_realized_pre       0
n_empty_realized_post      0
n_dur_le_0_pre             0
n_dur_le_0_post            0
n_empty_and_zerodur_pre    0
n_empty_and_zerodur_post   0
n_judgeable_pre            0
n_judgeable_post           0
n_judgeable_film_pre       0
n_judgeable_film_post      0
n_judgeable_other_pre      0
n_judgeable_other_post     0
n_judgeable_unassigned_film_pre  0
n_judgeable_unassigned_film_post 0
gap_contract_pp            0.05
gap_all_pp                 0.05
gap_excl_none_pp           0.05
gap_excl_zerodur_pp        0.05
agree_film_pre             0.0005
agree_film_post            0.0005
agree_other_pre            0.0005
agree_other_post           0.0005
did_film_pp                0.05
rare_share_pre             0.0005
rare_share_post            0.0005
rate_tone_pre_pm           0.5
rate_tone_post_pm          0.5
rate_segment_pre_pm        0.5
rate_segment_post_pm       0.5
rate_diff_pre_pm           0.5
rate_diff_post_pm          0.5
rate_none_pre_pm           0.5
rate_none_post_pm          0.5
```

各自的算法：

- `n_match_*` 是**可判集内**的匹配数，不是该期全部匹配数。
- `n_empty_and_zerodur_*` 是 `jp_realized` 为空**且** `dur<=0` 的音节数。恒等式 `n_judgeable = n_total - n_empty_realized - n_dur_le_0 + n_empty_and_zerodur` 必须成立；两条算路里有一条把 `n_judgeable_*` 写成这个 `derived:` 式子最好，另一条直接数集合，这样恒等式本身也被验了一遍。
- `gap_contract_pp` 是 `agreement(pre) - agreement(post)`，用契约第 24 条的可判集。
- `gap_all_pp`、`gap_excl_none_pp`、`gap_excl_zerodur_pp` 是同一个差换三种口径。**每一种的分子都要跟着分母一起换**：全部 A+B 音节 / 全部匹配；只剔除 `jp_realized` 为空的行（即 `jp_match='none'`）/ 剩下的行里的匹配；只剔除 `dur<=0` 的行 / 剩下的行里的匹配。三者只用于稳健性对照。
- `agree_*` 四个是 film/other × pre/post 的四格一致率，分子分母都在可判集内。
- `did_film_pp = (agree_film_pre - agree_film_post) - (agree_other_pre - agree_other_post)`。
- `rare_share_*` 是稀有字音节占该期 A+B 音节的比例。
- `rate_<verdict>_<period>_pm` 是该期 A+B 中该 `jp_match` 取值的千分比，分母是该期 A+B 全部音节。
- `n_unassigned_period` 与 `n_unassigned_film` 是两个分组谓词都没匹配上的视频数。今天应当都是 0；容差是 0，所以将来语料一变就会红。
- `n_judgeable_unassigned_film_*` 是 `title` 为空的视频上、该期内发布集的可判音节数。今天应当都是 0；容差是 0。它们是 film/other 三端恒等式的第三项，不能用 `n_unassigned_film`（视频数）代替。
- `n_dur_le_0_*` 同时是 `gap_excl_zerodur_pp` 那一版被剔除的行数（契约第 25 条要求声明）。

## 怎么交这 41 个数字

两个 agent 交的是**同一种文件**，形状一样，都不含任何判定字段：

```
worker    tasks/TASK-6/results.json
verifier  tasks/TASK-6/mine.json

[{"name": …, "value": <数>, "n": <整数>, "query": "…"}]
```

谁都不写 `match`，也不写 `abs_diff`。比对由 `output-check` 做。

`query` 是这个数字的算路，`output-check` 会**照着它把每个数字重新跑一遍**，跑出来的和你写下的不一致就红。只有两种形式：

- **`tasks/TASK-6/sql/<名>.sql`**（worker）或 **`tasks/TASK-6/mine_sql/<名>.sql`**（verifier）：一个文件一条语句，`SELECT` 或 `WITH` 开头，返回**恰好一行一列**，那一格就是这个数字。
- **`derived:<表达式>`**：只能用这 41 个名字里的其他名字、数字、`+ - * /` 和括号。例如
  `derived:100 * (n_match_pre / n_judgeable_pre - n_match_post / n_judgeable_post)`。
  重放时代进去的是**重放出来的**输入值，不是你写下的值——所以把输入写错、再把推导写成与错输入自洽，两行都会红。

两条约束：一个 `.sql` 文件只能支撑一个数字；worker 与 verifier 不得指向同一个 `.sql` 文件，所以两个目录分开。`derived:` 两边写成一样没问题，它的每个输入都各自被重放过。

41 个数字每一个都必须落进这两种形式之一。这确实限制了写法，换来的是从此没有一个数字只是「写在那里」。开工前先定下哪些走 SQL、哪些走 `derived:`。`n_judgeable_unassigned_film_*` 必须走 SQL：写进 `derived:` 会让下面的 film/other 恒等式在该文件上被跳过。

## `n` 是什么

`n` 是这个数字**算在多少行语料上**。两条算路必须给出完全相同的 `n`，且每个 `n` 必须等于下面 ```n``` 块里声明的常数或 `derived:` 表达式（代入的是重放出来的值，不是 agent 写下的值）。只两边相等不够：两边一起抄 `1` 也会相等。

```n
# name                     n
n_videos_pre               567
n_videos_post              567
n_unassigned_period        567
n_unassigned_film          567
n_total_pre                derived:n_total_pre
n_total_post               derived:n_total_post
n_match_pre                derived:n_total_pre
n_match_post               derived:n_total_post
n_empty_realized_pre       derived:n_total_pre
n_empty_realized_post      derived:n_total_post
n_dur_le_0_pre             derived:n_total_pre
n_dur_le_0_post            derived:n_total_post
n_empty_and_zerodur_pre    derived:n_total_pre
n_empty_and_zerodur_post   derived:n_total_post
n_judgeable_pre            derived:n_total_pre
n_judgeable_post           derived:n_total_post
n_judgeable_film_pre       derived:n_total_pre
n_judgeable_film_post      derived:n_total_post
n_judgeable_other_pre      derived:n_total_pre
n_judgeable_other_post     derived:n_total_post
n_judgeable_unassigned_film_pre  derived:n_total_pre
n_judgeable_unassigned_film_post derived:n_total_post
gap_contract_pp            derived:n_judgeable_pre + n_judgeable_post
gap_all_pp                 derived:n_total_pre + n_total_post
gap_excl_none_pp           derived:n_total_pre + n_total_post
gap_excl_zerodur_pp        derived:n_total_pre + n_total_post
agree_film_pre             derived:n_judgeable_film_pre
agree_film_post            derived:n_judgeable_film_post
agree_other_pre            derived:n_judgeable_other_pre
agree_other_post           derived:n_judgeable_other_post
did_film_pp                derived:n_judgeable_film_pre + n_judgeable_film_post + n_judgeable_other_pre + n_judgeable_other_post
rare_share_pre             derived:n_total_pre
rare_share_post            derived:n_total_post
rate_tone_pre_pm           derived:n_total_pre
rate_tone_post_pm          derived:n_total_post
rate_segment_pre_pm        derived:n_total_pre
rate_segment_post_pm       derived:n_total_post
rate_diff_pre_pm           derived:n_total_pre
rate_diff_post_pm          derived:n_total_post
rate_none_pre_pm           derived:n_total_pre
rate_none_post_pm          derived:n_total_post
```

## 抽样框

下面 ```frame``` 块在出现 `videos_expected` 时激活恒等式
`n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected`
（容差 `videos_expected_tol`；未写则按 0）。没有这块、或没有 `videos_expected` 时，该条恒等式不运行。检查读的是这个字段，不得把 567 写进闸门脚本。

```frame
windows.tier IN ('A','B')
videos_expected 567
videos_expected_tol 0
```

## 恒等式

下面 ```identities``` 块每一行是 `<expr> = <expr>  <tol>`。`output-check` 用与 `derived:` 相同的 AST，代入**该文件重放出来的**值（不合并 worker 与 verifier 的字典）。`frame.<字段>` 绑定上面 ```frame``` 块的数值。一条恒等式**只在该文件里每一个出现的数字名都是 SQL 算路时才计**；任一名字是 `derived:` 就跳过——否则 worker 把 `n_judgeable_pre` 写成推导式时，film/other 恒等式在该文件上会变成恒真。

```identities
n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected  0
n_judgeable_film_pre + n_judgeable_other_pre + n_judgeable_unassigned_film_pre = n_judgeable_pre  0
n_judgeable_film_post + n_judgeable_other_post + n_judgeable_unassigned_film_post = n_judgeable_post  0
```

## 还要交的东西（这部分不进 numbers 块）

**一个分解**：期间差距里，多少由可观测变量的组成差异解释，剩下多少。用哪些变量、怎么标准化，由你决定，但必须声明选了什么、为什么、每个变量从哪来。剩余差距要带按 `video_id` 整簇 bootstrap 的区间。

**一条对剩余部分的具体假设**，写成「用什么数据、做什么比较、什么结果会否定它」。写不成这个形式的就不要提。

**一句话结论**。

这部分两条算路不会一致，也不要求一致——它由 Tom 和 `auditor` 判断，不由 `output-check` 判断。

## 已知的坑

`tier`、`coverage`、`chars_per_sec`、`aligned` 是被评估模型自己的产物（契约第 27 条）：用它们分层就要同时报未分层的那一版。

`dur > 0` 不得单独用作筛选条件（第 25 条）。`review_prior` 不得用来分层、过滤或加权（第 26 条）。

按年切分时每格的视频数要一并报出来：2021 和 2023 的样本很小，别把小格当趋势。

## 分工

`worker` 与 `verifier` **同时启动，从同一个 `starting_ref`**。不是一个做完另一个再做：`output-check` 会检查引入你那个文件的 commit，它的树里不能有对方的文件，所以谁在对方合入之后才切分支，谁就红。

- `worker`，分支 `cursor/t6-worker-…`：写 `tasks/TASK-6/sql/`、`src/`、`tests/`，交 `tasks/TASK-6/results.json` 与上面那部分开放分析。
- `verifier`，分支 `cursor/t6-verifier-…`：**不读 worker 的代码、对话、PR**，只读本文件和语料，用自己的 SQL 把这 41 个数字重算一遍，写 `tasks/TASK-6/mine_sql/`，交 `tasks/TASK-6/mine.json`。
- 不一致的行发回去重算。同一个输出文件最多被改三次——第一次加两次重试，`output-check` 数 commit。仍不一致就停，两套数字一起升级给 Tom。
- 两个都合入、`output-check` 报出 41 个全一致之后，把本文件的 `status:` 改成 `closed`，并写入一行 `corpus_sha:`，值为当时 `README.md` 里的语料 sha256。stamp 与当前 pin 不符或缺失时本任务是 STALE：不再重放，不参与红绿，也不打印 41/41 agree。改不动 `closed` 就说明还没齐，那是检查在告诉你事实。然后放 `auditor`，写 `review/TASK-6/audit.md`。

两个 agent 都不能改本文件，但**必须**能写 `tasks/TASK-6/` 下面自己的产出。
