# LOOP

一个任务从提出到收口的全过程。没有轮次，没有阶段号，没有波次表。

## 三个节点

| 节点 | 读什么 | 写什么 | 分支 |
|---|---|---|---|
| `worker` | 任务书、语料 | `tasks/TASK-N/results.json` 与产生它的 SQL | `cursor/t<N>-worker-…` |
| `verifier` | 任务书、语料 | `tasks/TASK-N/mine.json` 与产生它的 SQL | `cursor/t<N>-verifier-…` |
| `auditor` | 本任务的 commit 与 PR 正文 | `review/TASK-N/audit.md` | `cursor/t<N>-auditor-…` |

两个算数的节点交**同一种文件**，形状一样，都不含任何判定字段：

```
[{name, value, n, query}]
```

谁都不写「对不对」。比对由 `output-check` 做。上一版让 `verifier` 自己写 `abs_diff`
和 `match`，那等于让这条回路里唯一能失败的检查变成一份自述——被判的人填判决书。

`worker` 与 `verifier` **同时从同一个 `starting_ref` 启动**，不读对方的代码，不 import
对方的任何模块。谁先合入不重要。一个 agent 和检查它的 agent 共享上下文，就是同一个
agent 假装成两个。

## 五步

```
PLAN     Tom 写 tasks/TASK-N.md：数字名、定义、容差、status: open。
         只写名字、定义、容差，不写值——写了值就等于让两个 agent 抄同一个数。
EXECUTE  worker 与 verifier 从同一个 ref 出发，各自从语料算出这些数字。
CHECK    output-check 先按每个数字自己声明的算路重放它，再比对两套数字。
ITERATE  哪几个不一致，就只把那几行发回去，其余不动。并行的其他任务不受影响：
         一条不碰该任务的 PR 不会因为 main 上这份不一致而红。
STOP     全部一致 → 把任务书改成 status: closed，并盖上当时 README 的
         corpus_sha（语料 pin）。这一步本身要过 CI。
         stamp 与当前语料 pin 不符（缺或不等）→ 该关闭任务标 STALE，
         跳过重放，不参与红绿，也不打印 N/N agree（plan §4.5）。
         同一个文件被改到第四次 → 停，任务书改成 status: escalated，
         两套数字一起升级给 Tom。
         agent 走不下去（不能改闸门）→ 留一条空 commit，留言以 BLOCKED:
         开头；owner 把任务书改成 status: blocked。
         escalated 与 blocked 暂停该任务的重放、比对、改写计数。
         改任务书本身是一次 reset：从那次 commit 起重计改写次数。
         reopen 就是再写成 status: open。
```

上限是**三次**：第一次加两次重试。不是建议，`output-check` 数 commit。
改写次数从该任务书最近一次改动（reset commit）计起，所以 reopen 不会把上一轮的三次带走。

## 四道闸门

| 检查 | 管什么 |
|---|---|
| `output-check` | 每个数字都能从语料重放出来；SQL 的 `EXPLAIN QUERY PLAN` 必须 `SCAN`/`SEARCH` 语料表；每条语句执行两次必须得到同一个数；规范化后的语句不得出现 `random()` / `randomblob()` / `strftime('now')` 族；两套独立算出的数字必须相等；若任务书有 fenced `n` 块，每个 `n` 还必须等于块里声明的常数或 `derived:`（用重放值求），两套 `n` 仍须完全相等，两道检查一起做不是互相替代；若任务书有 fenced `identities` 块，每一行 `<expr> = <expr>  <tol>` 用与 `derived:` 相同的 AST 在**该文件**重放值上求（不合并 worker+verifier 字典）；`frame.<字段>` 绑定 ```frame``` 块数值；一条恒等式只在该文件里每个数字名都是 SQL 算路时才计，否则跳过；若 `frame` 含 `videos_expected` 且 numbers 声明了 `n_videos_pre` / `n_videos_post` / `n_unassigned_period`，三者重放值之和必须等于 `frame.videos_expected`（容差 `videos_expected_tol`，未写则 0），没有 `videos_expected` 时此条不运行；重写次数有上限（从 reset commit 计起）；两条分支不得从对方的答案出发（引入 commit 的整段祖先里都没有另一边的文件；两边引入 commit 无祖先关系、不同分支、不同作者）；`status: closed` 只有在两边齐、全一致时才允许，收口时写入一行 `corpus_sha:`（当时 README 的语料 pin）；关闭任务 stamp 缺失或与当前 pin 不符 → **STALE**，跳过重放/比对/改写计数，不参与红绿，不打印 `N/N number(s) agree`（plan §4.5）；`status: escalated` 与 `status: blocked` 暂停该任务的重放、比对、改写计数；空 commit 且留言以 `BLOCKED:` 开头会被认出并打印；**pull request 上只完整检查这次 diff 碰到的任务**（任务书或 `tasks/TASK-N/`，任一边输出文件都算碰到），其余任务只打 frozen summary，`status: open` 的不一致不能把无关 PR 打红；main 上仍检查全部任务；**`tasks/` 下任一 TASK-N 目录里有 `results.json` 或 `mine.json`，但顶层 glob `tasks/TASK-*.md` 找不到对应任务书 → 红**（把任务书移出 glob 不得让检查变成 no-op 绿灯）；**同一 job 另跑 `python scripts/relations.py`（HEAD 工作树，不是 `/tmp/gate`）**：把语料拷到 `$RUNNER_TEMP`（从不写进 `data/`），`videos`/`windows`/`syllables` 整表再插一遍（主键加 `dup:` 前缀，`video_id`/`uid` 跟着改；`syllables.char` 同样加前缀，否则 `rare_share_*` 的绝对频次阈值 `< 10` 在翻倍后会动），`n_*` 必须恰好翻倍，`agree_*`/`rare_share_*`/`rate_*_pm`/`gap_*`/`did_*` 必须落在原容差内；再按 `INSERT ... ORDER BY random()` 重建三表，每个声明数字必须与原语料重放一致。A1 之后 PR 上的 `output_check.py` 来自 base，所以这一步必须从本次 checkout 调 `relations.py`，不能塞进 `/tmp/gate/output_check.py`。relations 不做 PR freeze：关掉的任务里写死的分母也必须能把任何 PR 打红 |
| `scope-check` | 分支必须属于已知类别（先匹配 agent 前缀）；repair/ 与 chore/ 不能单靠前缀授权，须 `github.actor` 落在仓库 owner allowlist 上；chore 与 agent 同受 DENY；agent 不得碰 `.cursor/` `.github/` `data/` `scripts/`、`README.md`、`LOOP.md`，也不得改任务书 `tasks/TASK-N.md`，但必须能写 `tasks/TASK-N/` 下面自己的产出 |
| `history-audit` | 移动已有的栅不得与被它度量的东西同 PR，且正文须有 `BAR-CHANGE:` 并点名每个被移动的栅路径；被度量路径是 files 减去栅路径（闸门脚本 fail-site 净删算移动栅，但不自己锁自己）；`tasks/**/*.sql` 属被度量；任务书 fenced `numbers`/`fixture`/`frame`/`n` 里放宽容差、删名字或删整块算移动栅，收窄容差不算；死路径栅移入 `RETIRED` 块而非删除，live∪RETIRED 的 glob 丢失才算删栅 |
| `tests` | 有 `tests/test_*.py` 时跑 pytest |

前三个是 main 的必需检查。

## output-check 实际做了什么

按顺序，任何一条不过就红。**在 pull request 上，下面 2–9 条只作用于这次 diff 碰到的任务**（`tasks/TASK-N.md` 或 `tasks/TASK-N/` 下任何文件，包括只改 `results.json` 或只改 `mine.json`）。没碰到的任务打一行 frozen summary，不把失败并进总账——`status: open` 且两边已经不合的任务（ITERATE）因此不能挡住一条无关的 PR。没有 `--base-ref` 时（main 上的 push）仍走完全部任务。任务书发现是顶层 glob `tasks/TASK-*.md`（非递归）。**若 `tasks/` 下任一 TASK-N 目录里有 `results.json` 或 `mine.json`，而对应的 `tasks/TASK-N.md` 不在该 glob 里，这一条对整棵树生效、不受 PR freeze 跳过**（plan §2.6）：把任务书移走不得让检查变成「nothing to check」绿灯。

1. `data/corpus_v2.sqlite` 的 sha256 与 `README.md` 里记的一致。语料不对，后面全部无意义。
2. 任务书有且只有一行 `status: open` / `closed` / `escalated` / `blocked`，`numbers` 块能解析。可选一行 `corpus_sha:`（64 位小写 hex，可带反引号）：收口时盖上当时 README 的语料 pin。可选的 fenced `n` 块、`frame` 块与 `identities` 块也在这里解析。`escalated` 与 `blocked` 暂停该任务第 3–9 条（重放、比对、声明 n、恒等式、改写计数）。**`status: closed` 且 stamp 缺失或与当前 README pin 不符 → STALE**：第 3–9 条不跑，不把失败并进总账，也不打印 `N/N number(s) agree`（plan §4.5）。顶层 glob 找不到任务书、但对应 TASK-N 目录里还有 `results.json` 或 `mine.json`：直接红，不走「nothing to check」。
3. 两个输出文件的每一行恰好是 `{name, value, n, query}`，名字集合与 `numbers` 块**相等**——少一个和多一个都红；同一文件内不得有重名，也不得有两个数字共用一条算路。算路按 `route()` 解析后的路径计（`sql/../sql/x.sql` 与 `sql/x.sql` 是同一条），不是按 query 字符串。若有 `n` 块，其名字集合必须与 `numbers` 相等；每一行是非负整数常数或 `derived:` 表达式。
4. 每个 `query` 是下面两种之一：
   - `tasks/TASK-N/<…>.sql`：一条语句，`SELECT` 或 `WITH` 开头，返回恰好一行一列；`EXPLAIN QUERY PLAN` 必须出现对语料表 `videos` / `windows` / `syllables` / `runs` 的 `SCAN` 或 `SEARCH`（`SELECT 12345` 过不了这一关）；同一条语句执行两次结果必须相同；`strip_and_split` 之后不得出现 `random()`、`randomblob()`、`strftime('now')` 族；
   - `derived:<expr>`：只用其他已声明的数字名、数字、`+ - * /` 和括号。
5. 同一个 `.sql` 文件不得同时出现在两个文件里；`strip_and_split` 之后的语句文本 sha256 两边也不得相交（把 `sql/` 拷进 `mine_sql/` 过不了这一关）。定义可以共享，**实现不行**。`derived:` 允许两边写成一样，因为它的每个输入都各自被重放过。
6. 每个数字都等于它自己那条算路跑出来的结果，误差在容差内。`derived:` 用的是**重放出来的**值，不是 agent 自己写下的值——所以「把输入写错、再把推导写成与错输入自洽」这条路是走不通的，两行都会红。
7. 两套数字每个 `value` 在容差内相等，每个 `n` 完全相等。不一致的把两个数都打出来。只两边 `n` 相等不够（plan §2.5）：若有 `n` 块，每个写下的 `n` 还必须等于声明的常数或 `derived:`（代入的是重放值）。两道检查一起做。没有 `n` 块时，声明 n 那一道不激活。若有 `identities` 块，每一行 `<expr> = <expr>  <tol>` 用重放值求；只在**该文件**里每个数字名都是 SQL 算路时才计，否则跳过（不合并两边的字典）。若 `frame` 含 `videos_expected`，且 numbers 声明了 `n_videos_pre`、`n_videos_post`、`n_unassigned_period`，三者重放值之和必须等于 `frame.videos_expected`（容差 `videos_expected_tol`，未写则 0）。RHS 引用 frame 字段，检查代码里不得写死 567。没有 `videos_expected`、或该任务没声明那三个名字：该条不运行。
8. 动过同一个输出文件的 commit 不超过三个，从该任务书最近一次改动那个 reset commit 计起。`escalated` / `blocked` 不计。
9. 引入某一边文件的那个 commit，它自己的树和**所有祖先**的树里都没有另一边的文件。两边的引入 commit 不能有祖先关系，必须来自不同分支、不同作者（plan §2.7）。只看引入 commit 自己那一棵树，挡不住「先提交自己的、再 merge 对方」或同一条分支上分三次写出两边。

同一 job 里、在 `/tmp/gate/output_check.py`（PR）或 `scripts/output_check.py`（main）之后，另跑 `python scripts/relations.py`。这一步读的是 **HEAD 工作树**，不是 `/tmp/gate`：A1 之后 PR 上的闸门脚本是 base 的拷贝，新加的 `relations.py` 在合入之前 base 看不见。临时语料只写 `$RUNNER_TEMP`（或本地 tempfile），跑完删除，**从不写进 `data/`**。它不做 PR freeze。数字来自重放，不来自 agent 写下的值。

## 任务书状态

| status | 谁写 | 闸门 |
|---|---|---|
| `open` | Tom 开题 | 重放、比对、改写计数 |
| `closed` | chore 收口 | 同上，且两边必须齐、必须一致。收口时写入 `corpus_sha:`（当时 README pin）。stamp 缺失或与当前 pin 不符 → STALE：跳过重放/比对/改写计数，不参与红绿，不打印 N/N agree |
| `escalated` | Tom / chore | 暂停重放、比对、改写计数。改写到顶，两套数字交给 Tom |
| `blocked` | Tom / chore | 暂停同上。走不下去 |

agent 不能改任务书。它要停的时候留下一条**空 commit**，第一行以 `BLOCKED:` 开头，例如 `BLOCKED: TASK-7 cannot touch scripts/`。这条 commit 与父 commit 同树，merge 之后 git log 里还能看见——这就是 durable marker。`output-check` 认出这种 commit 并打印；真正暂停检查的是任务书上的 `status: blocked` 或 `status: escalated`。

**reset commit**：任何一次改 `tasks/TASK-N.md` 都是一次 reset。改写次数从那次 commit 之后重计。**reopen** 就是 chore 把 `escalated` / `blocked` / `closed` 改回 `open`；这一步本身是一次 reset，所以不会撞上一轮的三次上限。

## 它证明什么，不证明什么

值得把这几条分开说，因为混在一起就会变成过强的结论。

**重放**证明「这句 SQL 跑出来确实是这个数」。它不证明这句 SQL 问的是对的问题。

**两套独立算路**证明这个问题被两条不同的路各问了一遍。它不证明两条都对——两个
agent 可以同样地错，只是用不同的 SQL 同样地错要难得多。

**第 9 条**证明两边的引入 commit 在历史上是分开的：彼此不是祖先、不是同一条
分支上的两次提交、不是同一个作者，而且引入 commit 的祖先里也没有对方的文件。
只检查引入 commit 自己的树，等于只挡住最简单的顺序（先 merge 对方，再提交自己）。
它**仍然不**证明这个 agent 在运行途中没有去 fetch 对方的分支——CI 里没有任何东西
能证明这件事，那要靠 `auditor` 读历史。两个 agent 从同一个 ref 启动、用不同的
git 作者身份，第 9 条对两边都自然成立。

**任务书里的开放分析**——比如「标准化之后还剩多少差距」——取决于 agent 自己选的变量，
两个 agent 不会一致，也不该强求。这部分不进 `numbers` 块，由 Tom 和 `auditor` 判断。
判断不能自动化。硬把它塞进闸门，只会得到一个假的绿灯。

分支本身就是断点：哪些 commit 在，就说明做到哪一步了。不另设状态文件。

## 收口

`worker` 与 `verifier` 都合入、`output-check` 报出全部一致之后，把任务书改成
`status: closed`，并写一行 `corpus_sha:`，值为当时 `README.md` 里的语料
sha256——这一步自己也要过 `output-check`，所以两边没齐或有一个数字不一致
时，改不动。stamp 与当前 pin 一致的关闭任务仍会重放；不一致或缺失则标
**STALE**，跳过重放，不参与红绿，**不打印** `N/N number(s) agree`。

keep rate 抄的是 live closed 任务那一行 `N/N number(s) agree`。STALE 不是
39/39，不得把 STALE 跳过当成留下了全部数字。

然后放 `auditor`：读这批 commit 的 patch 与每个 PR 的正文，答六个固定问题，每条结论带
commit sha、文件、行号，给不出就写 UNKNOWN。它只写 `review/TASK-N/audit.md`，不得改
任何代码、测试、声明或栅。

它的结论**只进 `backlog.md`**，永远不直接变成下一个任务的题目。否则这台专门生产过程
缺陷的机器会一直吃掉轮次。

收口时在 `backlog.md` 记一行 keep rate：这个任务产出了几个数字，留下了几个。连续低于
一半，下一个任务不派 agent，自己做。数字来自 live closed 的 `N/N agree`，不是 STALE。

## 语料更换

语料变动走 `repair/` PR（agent 碰不了 `data/` 与 `README.md`）：**同一条 PR**
里改 `data/corpus_v2.sqlite`、`README.md` 的 sha256 pin，以及每份
`status: closed` 任务书上的 `corpus_sha`。只改 README 不改 stamp，关闭任务
变成 STALE（跳过重放，不红，也不打 N/N agree）。要让关闭任务继续活着，stamp
必须改成新 pin，并且数字仍能在新语料上重放——活着的关闭任务不会因为「两边写
下的值彼此相等」就绿灯，重放对的是新语料。
