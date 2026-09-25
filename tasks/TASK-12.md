# TASK-12：文字侧三工具 + jp_default 基线相对 jp_realized 的一致率（主集=至少两工具读音不同）

status: open
corpus_sha: 2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f
rung: Autopilot

## 目标

在发布集可判定音节上，比较 ToJyutping（语料列 `jp_ctx`）、PyCantonese、g2pW-Cantonese 与基线永远 `jp_default` 相对 `jp_realized` 的一致率；主评测集由纯文字侧定义（至少两个工具规范化后读音不同）。各工具相对 default 的配对差交 `video_id` 整簇 bootstrap 区间（区间不进 `numbers`）。**结论只声称每个 gap 相对 0（及相对幅度是否翻转），禁止跨工具比较 gap 大小。** TASK-11 子集、逐字分歧表、非句末「呢」仅描述。两边各自跑开源 CPU 文字工具；不碰音频，不改 `data/`。本任务书的 `numbers` 块不写任何结果值。

## Prior Attempts

上一轮是 TASK-11（`tasks/TASK-11.md`，已 `closed`）：词典侧 `jp_ctx≠jp_default` 子集上 ctx vs default。本任务是 campaign `investigations/g2p-real-speech` 方向一的下一步：引入 PyCantonese / g2pW 预测表（闸门 #130），主集改为「至少两工具文字侧不同」。提案经 Tom「采纳」（修订版：质询员打回 Q4/Q7 已并入——Q4 公式写死且不跨工具比 gap；Q7 主集与对照侧各一份）。

## 假说

数据：发布集音节。主评测集上：

- `agree_tj_pm` / `agree_py_pm` / `agree_g2pw_pm` / `agree_default_pm`：各工具或基线与 `jp_realized` 的一致率（千分之一）。
- `gap_tj_default_pm` / `gap_py_default_pm` / `gap_g2pw_default_pm`：各自减去 `agree_default_pm`。正值表示该工具在该子集上比永远 default 更常与声学读音整串一致。

主结论可谈每个 gap 相对 0（用对应 CI）；**禁止**只凭两个各自对 0 的区间说「工具 A 的 gap 比工具 B 大」，也禁止跨工具比 gap。禁止把一致率写成准确率 / 错误率。禁止写「not supported」。

否定假说：三个 gap 均与 0 一致（开放分析按整簇区间判断），或换成相对幅度后符号/结论翻转（须写明）。

## 输入

只读 `data/corpus_v2.sqlite`。读之前先算它的 sha256 并与 `README.md` 比对，不符就退出非零。`jp_ctx` / `jp_default` 用语料列（ToJyutping 版本以语料为准）。PyCantonese 与 g2pW-Cantonese：两边各自写推理脚本、各跑一遍，只处理文字、开源 CPU；预测写入本侧 `pred/` 或 `mine_pred/`（见下），版本钉死进对应 `.run.json`。不碰音频，不改数据库。不读、不改 TASK-6–11 的算路文件。

## 定义（两条算路必须用同一套）

- **发布集**：`windows.tier IN ('A','B')`（音节经窗加入；若用 `syllables.tier` 须与窗一致）。任何关于发布集的统计都显式过滤 tier，并在 `manifest.json` 记录被这条规则丢掉的行数。
- **可判定（契约第 24 条）**：`jp_realized` 非空（trim 后长度 > 0）且 `dur > 0`。可判定行上若参与比较的词典列（`jp_ctx` / `jp_default`）为 NULL 或 trim 后为空，退出非零。pred 表行的校验由闸门负责（未知 id / 空 hyp / 重复 id）。
- **规范化（写死）**：比较前对字符串做 trim，再按 Unicode casefold（大小写不敏感）。含调号；不作 tone-stripped；不作候选集命中匹配。
- **一致谓词（写死）**：在可判定行上，左侧（`jp_ctx` 列，或 `pred_pycantonese.hyp` / `pred_g2pw.hyp`，或 `jp_default` 列）与 `jp_realized` 经上述规范化后**整串相等**。**不得**用 `jp_match` 列作分子。
- **三工具读音**：
  1. ToJyutping：`syllables.jp_ctx`
  2. PyCantonese：表 `pred_pycantonese`（`id`=`syl_id`，`hyp`）
  3. g2pW-Cantonese：表 `pred_g2pw`
- **主评测集（纯文字侧）**：发布集 ∩ 可判定 ∩（三工具规范化后至少有一对不等）。禁止按 `jp_match` / `jp_realized` 取值 / 声学列筛选进样。
- **对照侧（Q5 规模）**：发布集 ∩ 可判定 ∩（三工具规范化后两两全等），计数为 `n_tools_agree`。
- **`n_multi_disagree`**：主评测集行数。
- **`n_tj_match` / `n_py_match` / `n_g2pw_match` / `n_default_match`**：主评测集上一致谓词对各侧为真的行数。
- **`agree_*_pm`**：`1000 * n_*_match / n_multi_disagree`。分母为 0 则退出非零。
- **`gap_X_default_pm`**：`agree_X_pm - agree_default_pm`（X∈{tj,py,g2pw}；定义恒等；配对在同一批主集行上）。
- **结论口径（Q4）**：只声称每个 `gap_X_default_pm` 相对 0，以及相对幅度是否翻转。**禁止**跨工具比较 gap 大小；不交两两工具差的区间名。
- **Q4 差值区间（不进 numbers）**：名字 `gap_tj_default_ci` / `gap_py_default_ci` / `gap_g2pw_default_ci`。方法：对 `video_id` **有放回重采样**整簇，`B >= 1000`；层种子 `int(sha256(f"{master_seed}:{h}").hexdigest()[:8], 16)`，与契约第 20 条及 TASK-9/10/11 对齐。第 h 次：按有放回抽得的簇多重集，取这些簇在主评测集上的**行并集**（同一簇抽中 k 次仍只计该簇行一次进并集），在该并集上按与声明相同的定义**重算全局**对应的 `gap_X_default_pm`，再由 B 次重算得区间。相对幅度 = `gap_X_default_pm / agree_default_pm`（分母 0 则标不可比）；开放分析必须写一句：符号/结论是否翻转。报 `G`（有主评测集行的视频数）；`G < 10` 发 `ci_unreliable=1`。**禁止**先在每一簇内各自算 gap 再对簇级差值做均值或分位。区间端点不进 `numbers`。
- **Q5 错分方向（写死）**：漏掉「本应不同却被标成相同」的行 → 主集偏「更容易见差」的子集，`|gap_*|` 可能偏大；把噪声差纳入主集 → gap 被稀释。两侧规模名 `n_multi_disagree` / `n_tools_agree` 均进 `numbers`。
- **描述性（不进 numbers，标 `descriptive=1`）**：
  1. **TASK-11 子集**：发布集 ∩ 可判定 ∩（规范化后 `jp_ctx ≠ jp_default`）上各工具 / default 的一致率描述（不作 headline）。
  2. **逐字分歧表**：主集上按 `char` 汇总三工具两两分歧计数（descriptive）。
  3. **非句末「呢」**：`char = '呢'`，且文本侧不是句末。`next_char` **是语料列** `syllables.next_char`。判定写死：`trim(coalesce(next_char,''))` 长度 > 0，且该值不属于句末标点集合。句末标点集合写死为：`。！？!?．…`（记入 `manifest.json` 的 `sent_final_punct`）。再 ∩ 发布集 ∩ 可判定。只报与各工具的一致率描述。
- **总体**：这个频道的 567 条视频。聚类停在 `video_id`。不写「粤语」或「Cantonese」。
- **用词**：agreement / 一致率；禁止 accuracy / 错误率。两边都不是真值。
- **pm**：千分之一尺度的一致率或一致率差。
- **RESULT 头条**：最多点名 3 个数字名（建议三个 `gap_*_default_pm`）。

## 要交的数字

下面是这个任务必须交出的全部数字。**这里只有名字和容差，没有值**。

```numbers
# name                           tol
n_multi_disagree                 0
n_tools_agree                    0
n_tj_match                       0
n_py_match                       0
n_g2pw_match                     0
n_default_match                  0
agree_tj_pm                      0.5
agree_py_pm                      0.5
agree_g2pw_pm                    0.5
agree_default_pm                 0.5
gap_tj_default_pm                0.5
gap_py_default_pm                0.5
gap_g2pw_default_pm              0.5
```

各自的算法见上。`n_*` 必须走 SQL。两条算路里有一条把 `agree_*_pm` 与 `gap_*_default_pm` 写成 `derived:` 最好，另一条直接查。不声明描述性子集的率名。

## 怎么交这 13 个数字

两个 agent 交的是**同一种文件**，形状一样，都不含任何判定字段：

```
worker    tasks/TASK-12/results.json
verifier  tasks/TASK-12/mine.json

[{"name": …, "value": <数>, "n": <整数>, "query": "…"}]
```

谁都不写 `match`，也不写 `abs_diff`。比对由 `output-check` 做。本 PR 只开任务书：不要在这一步提交 `results.json`、`mine.json`、`RESULT.json` 或 `launches.json`。

`query` 是这个数字的算路，`output-check` 会**照着它把每个数字重新跑一遍**，跑出来的和你写下的不一致就红。只有两种形式：

- **`tasks/TASK-12/sql/<名>.sql`**（worker）或 **`tasks/TASK-12/mine_sql/<名>.sql`**（verifier）：一个文件一条语句，`SELECT` 或 `WITH` 开头，返回**恰好一行一列**。可 JOIN `pred_pycantonese` / `pred_g2pw`（闸门按本侧 pred 装载）。
- **`derived:<表达式>`**：只能用这 13 个名字里的其他名字、数字、`+ - * /` 和括号。

两条约束：一个 `.sql` 文件只能支撑一个数字；worker 与 verifier 不得指向同一个 `.sql` 文件。数字名必须落在 relations 族里：`n_*` 翻倍；`agree_*_pm` 与 `gap_*` 落在原容差内。

## 预测文件

```pred
pycantonese
g2pw
```

每侧：`tasks/TASK-12/pred/<stem>.jsonl`（worker）或 `tasks/TASK-12/mine_pred/<stem>.jsonl`（verifier），每行 `{"id","hyp"}`；旁放 `<stem>.run.json`（`script_commit`、`model`、`model_revision`、`decoding`、`device`、`dirty: false`）。两边各写各的推理脚本、各跑一遍。

## `n` 是什么

```n
# name                           n
n_multi_disagree                 derived:n_multi_disagree
n_tools_agree                    derived:n_tools_agree
n_tj_match                       derived:n_multi_disagree
n_py_match                       derived:n_multi_disagree
n_g2pw_match                     derived:n_multi_disagree
n_default_match                  derived:n_multi_disagree
agree_tj_pm                      derived:n_multi_disagree
agree_py_pm                      derived:n_multi_disagree
agree_g2pw_pm                    derived:n_multi_disagree
agree_default_pm                 derived:n_multi_disagree
gap_tj_default_pm                derived:n_multi_disagree
gap_py_default_pm                derived:n_multi_disagree
gap_g2pw_default_pm              derived:n_multi_disagree
```

率与 match 的 `n` 都是主评测集可判定行数。`n_tools_agree` 的 `n` 是其自身计数。

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
gap_tj_default_pm = agree_tj_pm - agree_default_pm  0.5
gap_py_default_pm = agree_py_pm - agree_default_pm  0.5
gap_g2pw_default_pm = agree_g2pw_pm - agree_default_pm  0.5
agree_tj_pm = 1000 * n_tj_match / n_multi_disagree  0.5
agree_py_pm = 1000 * n_py_match / n_multi_disagree  0.5
agree_g2pw_pm = 1000 * n_g2pw_match / n_multi_disagree  0.5
agree_default_pm = 1000 * n_default_match / n_multi_disagree  0.5
```

## 还要交的东西（这部分不进 numbers 块）

**质询 Q4**：开放分析交三个 `gap_*_default_ci`（方法与公式见定义）；列出四个 `agree_*_pm` 与三个 `gap_*_default_pm`；写相对幅度是否翻转；写明不跨工具比 gap。区间端点不进 `numbers`。

**质询 Q5**：开放分析写错分方向句（见定义）；两侧规模即 `n_multi_disagree` / `n_tools_agree`。

**质询 Q7 框内取值分布**（必交，开放分析 + `manifest.json`，不进 `numbers`；**两组各一份**）：
1. 三工具两两分歧模式（`tj≠py` / `tj≠g2pw` / `py≠g2pw` 的组合计数）在**主集**与 **`n_tools_agree` 对照侧**各一份（对照侧上两两分歧应全为 0，显式写出）。
2. `char` 顶频描述：主集与对照侧各一份。
3. 描述性「呢」子集：句末判定结果分布；判定仅用列 `next_char`。
4. pred 覆盖：主集 / 对照侧上 `pred_pycantonese` / `pred_g2pw` 的 id 齐全性（缺行退出非零的依据写入 manifest）。

若某一依赖列在框内 distinct=1，必须显式写出并标 `q7_constant=1`。

契约第 24 条六计数（主评测集）：`n_total`、`n_match`（此处按一致谓词，不是 `jp_match`）、`n_judgeable`、`n_empty_realized`、`n_dur_le_0`、后两者交集 — 进 `manifest.json` / 开放分析。

`manifest.json` 记录每一步 `{step, rule, group, rows_before, rows_after}`，以及每个输入的 sha256、行数、列集和 git sha；钉死 `sent_final_punct`、规范化规则、工具包名与 `model_revision`。

开放分析另交：TASK-11 子集描述性 agreement；逐字分歧表。

**一句话结论**，只针对本任务写下的假说；不得暗示「更准」；不得跨工具比 gap；只谈一致率与各 `gap_*_default_pm` 相对 0。头条最多 3 个数字名。

## 已知的坑

契约第 24 条默认的 `n_match` 用 `jp_match`；本任务分子是左侧与 `jp_realized` 整串相等，二者不同。`review_prior` 不得用来分层、过滤或加权。`jp_realized` 训练标签来自词典侧，一致率可能被高估——报告必写。描述性子集不得升格进结论头条。pred 只装本侧声明 stem；SQL 不得读另一侧目录。

## 分工

`worker` 与 `verifier` **同时启动，从同一个 `starting_ref`**。

- `worker`，分支 `cursor/t12-worker-…`：写 `tasks/TASK-12/sql/`、`pred/`，交 `tasks/TASK-12/results.json` 与开放分析。
- `verifier`，分支 `cursor/t12-verifier-…`：不读 worker，写 `tasks/TASK-12/mine_sql/`、`mine_pred/`，交 `tasks/TASK-12/mine.json`。
- 不一致发回重算；同一输出文件最多改三次。仍不一致就停。
- 两个都合入且全一致后，`auditor` 收口：`status: closed` + `corpus_sha:`，写 `review/TASK-12/audit.md` 与 `RESULT.json`。

两个 agent 都不能改本文件。

## 质询字段

Q1 分组边界: 不适用 + 理由（主结果不是按序数切分的组间差；主集由文字工具两两相等性定义）
Q2 加权单位: 不适用 + 理由（主结果是同一子集上的一致率与配对差，不是两组行加权组间差）
Q3 是否恒等式: 不适用 + 理由（不是份额分解；gap 是定义差，不写「解释了」）
Q4 差值区间: 触发；交 gap_tj_default_ci / gap_py_default_ci / gap_g2pw_default_ci（公式见定义）；只声称各 gap 相对 0，不跨工具比大小；须写相对幅度是否翻转；区间不进 numbers
Q5 代理错分方向: 触发；两侧规模 n_multi_disagree / n_tools_agree 进 numbers；错分方向见定义
Q7 框内取值: 触发；三工具两两分歧模式与 char 顶频在主集与对照侧各一份；呢子集与 pred 覆盖见「还要交的东西」
