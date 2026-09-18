# LOOP

一个任务从提出到收口的全过程。没有轮次，没有阶段号，没有波次表。

## 三个节点

| 节点 | 读什么 | 写什么 | 分支 |
|---|---|---|---|
| `worker` | 任务书、语料 | `tasks/TASK-N/results.json` 与产生它的代码 | `cursor/t<N>-worker-…` |
| `verifier` | 任务书、语料 | `tasks/TASK-N/verify.json` | `cursor/t<N>-verifier-…` |
| `auditor` | 本任务的 commit 与 PR 正文 | `review/TASK-N/audit.md` | `cursor/t<N>-auditor-…` |

`verifier` **不读 worker 的代码，不 import 它的任何模块**，上下文全新。它拿到的只有任务书和语料。一个 agent 和检查它的 agent 共享上下文，就是同一个 agent 假装成两个。

## 五步

```
PLAN     Tom 写 tasks/TASK-N.md。里面有 numbers 块：要交的数字名和各自的容差。
         只写名字、定义、容差，不写值——写了值就等于让 agent 抄。
EXECUTE  worker 从语料算出这些数字，交 results.json。
CHECK    verifier 用自己的 SQL 独立算一遍，交 verify.json。
         output-check 机械比对两套数字。
ITERATE  有 match:false，就只把不匹配的那几行发回 worker。
STOP     全绿 → 收口。两次尝试用完仍不匹配 → 停，两套数字一起升级给 Tom。
```

上限是 **2 次**。不是建议，是防止它在一个解不开的问题上安静地烧钱。

## 四道闸门

| 检查 | 管什么 |
|---|---|
| `scope-check` | 分支必须属于已知类别；agent 不得碰 `.cursor/` `.github/` `data/` `tasks/` |
| `history-audit` | 移动已有的栅不得与被它度量的东西同 PR，且正文须有 `BAR-CHANGE:` |
| `output-check` | 输出文件的名字集合必须与任务书的 `numbers` 块相等；任何 `match:false` 即红 |
| `tests` | 有 `tests/test_*.py` 时跑 pytest |

前三个是 main 的必需检查。`output-check` 是这条回路里唯一**能真正失败**的检查：它比的是两条独立算路的结果，不是让谁给自己打分。

agent 不能改 `tasks/`，所以它改不了自己的标尺。

## 输出形状

```
results.json  [{name, value, n, query}]
verify.json   [{name, worker, mine, abs_diff, match}]
STATE.json    {step, attempt, start_commit, produced, blocked_on}
```

形状不对就红，不靠人去读。`query` 是产生这个值的 `sql/` 文件名——值必须能被别人重放。

## 断点

每个 agent 在每一步之后更新 `tasks/TASK-N/STATE.json`。中途死掉或被打断，下一个接手的读它，从 `step` 继续，不从零重来。

## 机械关得住的和关不住的

`numbers` 块里的数字定义完全确定，两条算路必须一致，这部分由 `output-check` 关死。

任务书里的开放分析——比如「标准化之后还剩多少差距」——取决于 agent 自己选的变量，两个 agent 不会一致，也不该强求。这部分不进 `numbers` 块，由 Tom 和 `auditor` 判断。

判断不能自动化。硬把它塞进闸门，只会得到一个假的绿灯。

## 收口

`worker` 与 `verifier` 都合入之后，放 `auditor`：读这批 commit 的 patch 与每个 PR 的正文，答六个固定问题，每条结论带 commit sha、文件、行号，给不出就写 UNKNOWN。它只写 `review/TASK-N/audit.md`，不得改任何代码、测试、声明或栅。

它的结论**只进 `backlog.md`**，永远不直接变成下一个任务的题目。否则这台专门生产过程缺陷的机器会一直吃掉轮次。

收口时在 `backlog.md` 记一行 keep rate：这个任务产出了几个数字，留下了几个。连续低于一半，下一个任务不派 agent，自己做。
