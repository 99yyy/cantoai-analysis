# TASK-11：词典侧 jp_ctx≠jp_default 子集上，jp_ctx 与 jp_default 相对 jp_realized 的一致率及配对差

status: open
rung: Autopilot

## 目标

在发布集可判定音节上，用纯词典侧定义的主评测集（`jp_ctx ≠ jp_default`），报告 `jp_ctx` / `jp_default` 各自相对 `jp_realized` 的一致率，以及二者配对差值；差值按 `video_id` 整簇 bootstrap 交区间（区间不进 `numbers`）。非句末「呢」与 `n_cand≥2` 集合仅作描述性 agreement。不重跑任何模型，不碰音频，不改 `data/`。本任务书的 `numbers` 块不写任何结果值。

## Prior Attempts

上一轮是 TASK-10（`tasks/TASK-10.md`，已 `closed`）。本任务是 campaign `investigations/g2p-real-speech` 方向一的首个 gated 任务，不是 TASK-6–10 的分叉：测量对象是词典侧「上下文读音相对默认读音发生变化」的子集上的一致率对比，不重报期际一致率或语速差距。

提案经 Tom「采纳」（含两处修改：主集改为 `jp_ctx ≠ jp_default`；恢复比较并交 Q4 差值区间）；质询员对修订版打回 Q5（缺 = 侧规模名），已并入 `n_same_judgeable`；其余放行意见并入下文。

## 假说

数据：发布集音节（经 `windows.tier IN ('A','B')`，音节表自带 `tier` 时须与之一致）。主评测集上：

- `agree_ctx_pm`：`jp_ctx` 与 `jp_realized` 的一致率（千分之一）。
- `agree_default_pm`：同一批行上 `jp_default` 与 `jp_realized` 的一致率。
- `gap_agree_pm`：`agree_ctx_pm − agree_default_pm`。正值表示在该子集上 `jp_ctx` 比 `jp_default` 与声学读音更常整串一致。

主结论可比较二者大小，但必须用 `gap_agree_pm` 的整簇 bootstrap 区间谈差；禁止只凭两个各自对 0 的区间说「更大」。禁止把一致率写成准确率 / 错误率。禁止写「not supported」。

否定假说的结果：`gap_agree_pm` 与 0 一致（开放分析按整簇区间判断；`numbers` 容差只约束重放），或换成相对幅度后结论翻转（须在开放分析写明是否翻转）。

## 输入

只读 `data/corpus_v2.sqlite`。读之前先算它的 sha256 并与 `README.md` 比对，不符就退出非零。不跑任何模型，不碰音频，不改数据库。不读、不改 TASK-6–10 的算路文件。工具钉死为语料已有 ToJyutping 3.2.0 列（`jp_ctx` / `jp_default` / `n_cand`）。

## 定义（两条算路必须用同一套）

- **发布集**：`windows.tier IN ('A','B')`（音节经窗加入；若用 `syllables.tier` 须与窗一致）。任何关于发布集的统计都显式过滤 tier，并在 `manifest.json` 记录被这条规则丢掉的行数。
- **可判定（契约第 24 条）**：`jp_realized` 非空（trim 后长度 > 0）且 `dur > 0`。可判定行上若参与比较的词典列（`jp_ctx` / `jp_default`）为 NULL 或 trim 后为空，退出非零。
- **规范化（写死）**：比较前对字符串做 trim，再按 Unicode casefold（大小写不敏感）。含调号；不作 tone-stripped；不作候选集命中匹配。
- **一致谓词（写死）**：在可判定行上，左侧工具列与 `jp_realized` 经上述规范化后**整串相等**。**不得**用 `jp_match` 列作分子，也不得默认等同 `jp_match IN ('exact_default','exact_alt')`（那会把「命中候选但不是左侧列」算进一致）。
- **主评测集（纯词典侧）**：发布集 ∩ 可判定 ∩（规范化后 `jp_ctx ≠ jp_default`）。禁止按 `jp_match` / `jp_realized` 取值 / 声学列筛选进样。
- **对照侧（Q5 规模）**：发布集 ∩ 可判定 ∩（规范化后 `jp_ctx = jp_default`），计数为 `n_same_judgeable`。
- **`n_diff_judgeable`**：主评测集行数。
- **`n_ctx_match`**：主评测集上一致谓词对 `jp_ctx` 为真的行数。
- **`n_default_match`**：主评测集上一致谓词对 `jp_default` 为真的行数。
- **`agree_ctx_pm`**：`1000 * n_ctx_match / n_diff_judgeable`。分母为 0 则退出非零。
- **`agree_default_pm`**：`1000 * n_default_match / n_diff_judgeable`。
- **`gap_agree_pm`**：`agree_ctx_pm - agree_default_pm`（定义恒等；配对在同一批 `n_diff_judgeable` 行上）。
- **Q4 差值区间（不进 numbers）**：名字 `gap_agree_ci`。方法：按 `video_id` 整簇 bootstrap，`B >= 1000`；层种子 `int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16)`，与契约第 20 条及 TASK-9/10 对齐；每一簇内用该视频主评测集行按与声明相同的定义重算 `gap_agree_pm`，再对簇重采样得区间。报 `G`（有主评测集行的视频数）；`G < 10` 发 `ci_unreliable=1`。开放分析必须写一句：把差值换成相对幅度（例如相对 `agree_default_pm`）后，符号/结论是否翻转。区间端点不进 `numbers`。
- **Q5 错分方向（写死）**：漏掉「本应不同却被标成相同」的行 → 主集偏「更容易见差」的子集，`|gap_agree_pm|` 可能偏大；把噪声差纳入 ≠ 侧 → `gap_agree_pm` 被稀释。两侧规模名 `n_diff_judgeable` / `n_same_judgeable` 均进 `numbers`。
- **描述性（不进 numbers，标 `descriptive=1`）**：
  1. **非句末「呢」**：`char = '呢'`，且文本侧不是句末：`next_char` 不属于句末标点集合，且 `next_char` 非空（即不是 `text_clean` 末字的常见情形）。句末标点集合写死为：`。！？!?．…`（记入 `manifest.json` 的 `sent_final_punct`）。再 ∩ 发布集 ∩ 可判定。只报与 `jp_ctx` 的一致率描述，不宣称已知答案或金标读音。
  2. **`n_cand ≥ 2` 集合**：发布集 ∩ 可判定 ∩ `n_cand >= 2` 上的 `jp_ctx` 一致率描述（覆盖面广，不作 headline）。
- **总体**：这个频道的 567 条视频。聚类停在 `video_id`。不写「粤语」或「Cantonese」。
- **用词**：agreement / 一致率；禁止 accuracy / 错误率。两边都不是真值。
- **pm**：千分之一尺度的一致率或一致率差。

## 要交的数字

下面是这个任务必须交出的全部数字。**这里只有名字和容差，没有值**。

```numbers
# name                           tol
n_diff_judgeable                 0
n_same_judgeable                 0
n_ctx_match                      0
n_default_match                  0
agree_ctx_pm                     0.5
agree_default_pm                 0.5
gap_agree_pm                     0.5
```

各自的算法见上。`n_*` 必须走 SQL。两条算路里有一条把 `agree_*_pm` 与 `gap_agree_pm` 写成 `derived:` 最好，另一条直接查。不声明描述性子集的率名。

## 怎么交这 7 个数字

两个 agent 交的是**同一种文件**，形状一样，都不含任何判定字段：

```
worker    tasks/TASK-11/results.json
verifier  tasks/TASK-11/mine.json

[{"name": …, "value": <数>, "n": <整数>, "query": "…"}]
```

谁都不写 `match`，也不写 `abs_diff`。比对由 `output-check` 做。本 PR 只开任务书：不要在这一步提交 `results.json`、`mine.json`、`RESULT.json` 或 `launches.json`。

`query` 是这个数字的算路，`output-check` 会**照着它把每个数字重新跑一遍**，跑出来的和你写下的不一致就红。只有两种形式：

- **`tasks/TASK-11/sql/<名>.sql`**（worker）或 **`tasks/TASK-11/mine_sql/<名>.sql`**（verifier）：一个文件一条语句，`SELECT` 或 `WITH` 开头，返回**恰好一行一列**。
- **`derived:<表达式>`**：只能用这 7 个名字里的其他名字、数字、`+ - * /` 和括号。

两条约束：一个 `.sql` 文件只能支撑一个数字；worker 与 verifier 不得指向同一个 `.sql` 文件。数字名必须落在 relations 族里：`n_*` 翻倍；`agree_*_pm` 与 `gap_*` 落在原容差内。

## `n` 是什么

```n
# name                           n
n_diff_judgeable                 derived:n_diff_judgeable
n_same_judgeable                 derived:n_same_judgeable
n_ctx_match                      derived:n_diff_judgeable
n_default_match                  derived:n_diff_judgeable
agree_ctx_pm                     derived:n_diff_judgeable
agree_default_pm                 derived:n_diff_judgeable
gap_agree_pm                     derived:n_diff_judgeable
```

率与 match 的 `n` 都是主评测集可判定行数。`n_same_judgeable` 的 `n` 是其自身计数。

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
gap_agree_pm = agree_ctx_pm - agree_default_pm  0.5
agree_ctx_pm = 1000 * n_ctx_match / n_diff_judgeable  0.5
agree_default_pm = 1000 * n_default_match / n_diff_judgeable  0.5
```

## 还要交的东西（这部分不进 numbers 块）

**质询 Q4**：开放分析交 `gap_agree_ci`（方法与公式见定义）；列出 `agree_ctx_pm`、`agree_default_pm`、`gap_agree_pm`；写相对幅度是否翻转。区间端点不进 `numbers`。

**质询 Q5**：开放分析写错分方向句（见定义）；两侧规模即 `n_diff_judgeable` / `n_same_judgeable`。

**质询 Q7 框内取值分布**（必交，开放分析 + `manifest.json`，不进 `numbers`）：
1. 发布集可判定上，规范化后 `jp_ctx ≠ jp_default` 与 `=` 的行数（与两个 `n_*` 对照）。
2. 主评测集内 `char` 的顶频描述（descriptive）；`n_cand` 在发布集可判定上的取值分布摘要。
3. 描述性「呢」子集：句末判定结果分布（非句末进子集 / 句末排除）计数。

若某一依赖列在框内 distinct=1，必须显式写出并标 `q7_constant=1`。

契约第 24 条六计数（主评测集）：`n_total`、`n_match`（此处按一致谓词，不是 `jp_match`）、`n_judgeable`、`n_empty_realized`、`n_dur_le_0`、后两者交集 — 进 `manifest.json` / 开放分析。

`manifest.json` 记录每一步 `{step, rule, group, rows_before, rows_after}`，以及每个输入的 sha256、行数、列集和 git sha；钉死 `sent_final_punct` 与规范化规则。

**一句话结论**，只针对本任务写下的假说；不得暗示「更准」，只谈一致率与 `gap_agree_pm` 相对 0。

## 已知的坑

契约第 24 条默认的 `n_match` 用 `jp_match`；本任务分子是左侧列与 `jp_realized` 整串相等，二者不同。`review_prior` 不得用来分层、过滤或加权。`jp_realized` 训练标签来自词典侧，一致率可能被高估——报告必写。描述性子集不得升格进结论头条。

## 分工

`worker` 与 `verifier` **同时启动，从同一个 `starting_ref`**。

- `worker`，分支 `cursor/t11-worker-…`：写 `tasks/TASK-11/sql/`，交 `tasks/TASK-11/results.json` 与开放分析。
- `verifier`，分支 `cursor/t11-verifier-…`：不读 worker，写 `tasks/TASK-11/mine_sql/`，交 `tasks/TASK-11/mine.json`。
- 不一致发回重算；同一输出文件最多改三次。仍不一致就停。
- 两个都合入且全一致后，`auditor` 收口：`status: closed` + `corpus_sha:`，写 `review/TASK-11/audit.md` 与 `RESULT.json`。

两个 agent 都不能改本文件。

## 质询字段

Q1 分组边界: 不适用 + 理由（主结果不是按序数切分的组间差；主集由词典列相等性定义）
Q2 加权单位: 不适用 + 理由（主结果是同一子集上的一致率与配对差，不是两组行加权组间差）
Q3 是否恒等式: 不适用 + 理由（不是份额分解；gap 是定义差，不写「解释了」）
Q4 差值区间: 触发；交 gap_agree_ci（video_id 整簇 bootstrap B>=1000）；结论可比较 ctx 与 default；须写相对幅度是否翻转；区间不进 numbers
Q5 代理错分方向: 触发；两侧规模 n_diff_judgeable / n_same_judgeable 进 numbers；错分方向见定义
Q7 框内取值: 交 jp_ctx≠jp_default 判定覆盖、n_cand 摘要、呢子集句末判定分布（见「还要交的东西」）
