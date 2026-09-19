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
ITERATE  哪几个不一致，就只把那几行发回去，其余不动。
STOP     全部一致 → 把任务书改成 status: closed，这一步本身要过 CI。
         同一个文件被改到第四次 → 停，两套数字一起升级给 Tom。
```

上限是**三次**：第一次加两次重试。不是建议，`output-check` 数 commit。

## 四道闸门

| 检查 | 管什么 |
|---|---|
| `output-check` | 每个数字都能从语料重放出来；两套独立算出的数字必须相等；重写次数有上限；两条分支不得从对方的答案出发；`status: closed` 只有在两边齐、全一致时才允许 |
| `scope-check` | 分支必须属于已知类别（先匹配 agent 前缀）；repair/ 与 chore/ 不能单靠前缀授权，须 `github.actor` 落在仓库 owner allowlist 上；chore 与 agent 同受 DENY；agent 不得碰 `.cursor/` `.github/` `data/`，也不得改任务书 `tasks/TASK-N.md`，但必须能写 `tasks/TASK-N/` 下面自己的产出 |
| `history-audit` | 移动已有的栅不得与被它度量的东西同 PR，且正文须有 `BAR-CHANGE:` |
| `tests` | 有 `tests/test_*.py` 时跑 pytest |

前三个是 main 的必需检查。

## output-check 实际做了什么

按顺序，任何一条不过就红：

1. `data/corpus_v2.sqlite` 的 sha256 与 `README.md` 里记的一致。语料不对，后面全部无意义。
2. 任务书有且只有一行 `status: open` 或 `status: closed`，`numbers` 块能解析。
3. 两个输出文件的每一行恰好是 `{name, value, n, query}`，名字集合与 `numbers` 块**相等**——少一个和多一个都红；同一文件内不得有重名，也不得有两个数字共用一条算路。
4. 每个 `query` 是下面两种之一：
   - `tasks/TASK-N/<…>.sql`：一条语句，`SELECT` 或 `WITH` 开头，返回恰好一行一列；
   - `derived:<expr>`：只用其他已声明的数字名、数字、`+ - * /` 和括号。
5. 同一个 `.sql` 文件不得同时出现在两个文件里。定义可以共享，**实现不行**。`derived:` 允许两边写成一样，因为它的每个输入都各自被重放过。
6. 每个数字都等于它自己那条算路跑出来的结果，误差在容差内。`derived:` 用的是**重放出来的**值，不是 agent 自己写下的值——所以「把输入写错、再把推导写成与错输入自洽」这条路是走不通的，两行都会红。
7. 两套数字每个 `value` 在容差内相等，每个 `n` 完全相等。不一致的把两个数都打出来。
8. 动过同一个输出文件的 commit 不超过三个。
9. 引入某一边文件的那个 commit，它的树里**没有**另一边的文件。

## 它证明什么，不证明什么

值得把这几条分开说，因为混在一起就会变成过强的结论。

**重放**证明「这句 SQL 跑出来确实是这个数」。它不证明这句 SQL 问的是对的问题。

**两套独立算路**证明这个问题被两条不同的路各问了一遍。它不证明两条都对——两个
agent 可以同样地错，只是用不同的 SQL 同样地错要难得多。

**第 9 条**证明这条分支不是从一棵已经放着对方答案的树上长出来的。这是现实中它会坏
掉的方式：第二个 agent 在第一个合入之后才启动，答案就摊在它的工作副本里。它**不**
证明这个 agent 在运行途中没有去 fetch 对方的分支——CI 里没有任何东西能证明这件事，
那要靠 `auditor` 读历史。两个 agent 从同一个 ref 启动，第 9 条对两边都自然成立。

**任务书里的开放分析**——比如「标准化之后还剩多少差距」——取决于 agent 自己选的变量，
两个 agent 不会一致，也不该强求。这部分不进 `numbers` 块，由 Tom 和 `auditor` 判断。
判断不能自动化。硬把它塞进闸门，只会得到一个假的绿灯。

分支本身就是断点：哪些 commit 在，就说明做到哪一步了。不另设状态文件。

## 收口

`worker` 与 `verifier` 都合入、`output-check` 报出全部一致之后，把任务书改成
`status: closed`——这一步自己也要过 `output-check`，所以两边没齐或有一个数字不一致
时，改不动。

然后放 `auditor`：读这批 commit 的 patch 与每个 PR 的正文，答六个固定问题，每条结论带
commit sha、文件、行号，给不出就写 UNKNOWN。它只写 `review/TASK-N/audit.md`，不得改
任何代码、测试、声明或栅。

它的结论**只进 `backlog.md`**，永远不直接变成下一个任务的题目。否则这台专门生产过程
缺陷的机器会一直吃掉轮次。

收口时在 `backlog.md` 记一行 keep rate：这个任务产出了几个数字，留下了几个。连续低于
一半，下一个任务不派 agent，自己做。
