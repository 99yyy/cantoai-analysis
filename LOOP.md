# LOOP

一个任务从提出到收口的全过程。没有轮次，没有阶段号，没有波次表。

## 唯一执行手册

本文件是本仓库唯一的执行手册。若 `.cursor/BUGBOT.md`、bot 描述或其他文档与本文件冲突，以本文件为准。分析断言仍见 `.cursor/rules/analysis-contract.mdc`。

## 三个节点

| 节点 | 读什么 | 写什么 | 分支 |
|---|---|---|---|
| `worker` | 任务书、语料 | `tasks/TASK-N/results.json` 与产生它的 SQL | `cursor/t<N>-worker-…` |
| `verifier` | 任务书、语料 | `tasks/TASK-N/mine.json` 与产生它的 SQL | `cursor/t<N>-verifier-…` |
| `auditor` | 本任务的 commit 与 PR 正文 | `review/TASK-N/audit.md` 与 `tasks/TASK-N/RESULT.json` | `cursor/t<N>-auditor-…` |

两个算数的节点交**同一种文件**，形状一样，都不含任何判定字段：

```
[{name, value, n, query}]
```

谁都不写「对不对」。比对由 `output-check` 做。上一版让 `verifier` 自己写 `abs_diff`
和 `match`，那等于让这条回路里唯一能失败的检查变成一份自述——被判的人填判决书。

`worker` 与 `verifier` **同时从同一个 `starting_ref` 启动**，不读对方的代码，不 import
对方的任何模块。谁先合入不重要。一个 agent 和检查它的 agent 共享上下文，就是同一个
agent 假装成两个。

## 调查主题目录

`investigations/` 每个研究问题一个文件夹（kebab-case 主题名），放人写的笔记、探索脚本和索引。任务仍是测量单位：声明数字、SQL、`results.json` / `mine.json`、`RESULT.json` 只进 `tasks/TASK-N/` 与 `review/TASK-N/`，不得只写在调查目录里。调查文件夹不替代任务。

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
| `output-check` | 每个数字都能从语料重放出来；SQL 的 `EXPLAIN QUERY PLAN` 必须 `SCAN`/`SEARCH` 语料表；每条语句执行两次必须得到同一个数；规范化后的语句不得出现 `random()` / `randomblob()` / `strftime('now')` 族；两套独立算出的数字必须相等；若任务书有 fenced `n` 块，每个 `n` 还必须等于块里声明的常数或 `derived:`（用重放值求），两套 `n` 仍须完全相等，两道检查一起做不是互相替代；若任务书有 fenced `identities` 块，每一行 `<expr> = <expr>  <tol>` 用与 `derived:` 相同的 AST 在**该文件**重放值上求（不合并 worker+verifier 字典）；`frame.<字段>` 绑定 ```frame``` 块数值；一条恒等式只在该文件里每个数字名都是 SQL 算路时才计，否则跳过；期间恒等式是 ```identities``` 块里的普通一行，脚本不特例；重写次数有上限（从 reset commit 计起）；两条分支不得从对方的答案出发（引入 commit 的整段祖先里都没有另一边的文件；两边引入 commit 无祖先关系、不同分支、身份不同——身份 = author 与 committer 两者，只有 author 不同而 committer 相同会打印出来，因为 author 是自报的）；**open 任务里，PR 中每个动到某一边输出文件的 commit 都必须与该边引入 commit 同一身份**（一边不换手；把输出改进 merge commit 里也算动到）；**已关闭任务冻结**：任务书在 base 和 head 上都是 `closed` 时，PR 不得改 `tasks/TASK-N/` 下任何文件，要改先在任务书上改回 `status: open`（任务书只有 owner 能改）；`status: closed` 只有在两边齐、全一致时才允许，收口时写入一行 `corpus_sha:`（当时 README 的语料 pin）；关闭任务 stamp 缺失或与当前 pin 不符 → **STALE**，跳过重放/比对/改写计数，不参与红绿，不打印 `N/N number(s) agree`（plan §4.5）；`status: escalated` 与 `status: blocked` 暂停该任务的重放、比对、改写计数；空 commit 且留言以 `BLOCKED:` 开头会被认出并打印；**pull request 上只完整检查这次 diff 碰到的任务**（任务书或 `tasks/TASK-N/`，任一边输出文件都算碰到），其余任务只打 frozen summary，`status: open` 的不一致不能把无关 PR 打红；main 上仍检查全部任务；**`tasks/` 下任一 TASK-N 目录里有 `results.json` 或 `mine.json`，但顶层 glob `tasks/TASK-*.md` 找不到对应任务书 → 红**（把任务书移出 glob 不得让检查变成 no-op 绿灯）；字母后缀兄弟任务书 `TASK-N-b` / `-c` 的 ```numbers``` / ```n``` 必须与父任务书字节级相同（改容差不是分叉），`fork_depth` 上限 2，开 `-d` 红，父 RESULT 在子任务书落地后不得改删；**同一 job 另跑 `python scripts/relations.py`（HEAD 工作树，不是 `/tmp/gate`）**：把语料拷到 `$RUNNER_TEMP`（从不写进 `data/`），`videos`/`windows`/`syllables` 整表再插一遍（主键加 `dup:` 前缀，`video_id`/`uid` 跟着改；`syllables.char` 同样加前缀，否则 `rare_share_*` 的绝对频次阈值 `< 10` 在翻倍后会动），`n_*` 必须恰好翻倍，`agree_*`/`rare_share_*`/`rate_*_pm`/`gap_*`/`did_*` 必须落在原容差内；再按 `INSERT ... ORDER BY random()` 重建三表，每个声明数字必须与原语料重放一致。A1 之后 PR 上的 `output_check.py` 来自 base，所以这一步必须从本次 checkout 调 `relations.py`，不能塞进 `/tmp/gate/output_check.py`。relations 不做 PR freeze：关掉的任务里写死的分母也必须能把任何 PR 打红；**exclude**：再拷一份，按任务书 ```frame``` 块的谓词行（`<表>.<列> <SQL 片段>`，本项目是 `windows.tier IN ('A','B')`）删掉不在发布集里的行，再按配置里的外键把失去父行的子行一并删掉，然后重放；`frame` 含 `published_expected` 时每个声明数字必须与原语料重放一致（count 族精确，rate 族在容差内）——在错误集合上算出来的数字两边同错也过不了；任务书 fenced `outside_frame` 块列出的名字（按定义读 frame 之外的行，如 TASK-6 `rare_share_*`、TASK-7 `*_other_common_*` 的全库频次阈值）及由它们 `derived:` 出的名字不做 exclude 比较，每边打印豁免了哪些；**anchor**：`frame.published_expected` 必须等于排除后语料里单位表（配置 `unit_table`）的行数（`published_expected_tol`，未写则 0），对不上是 frame 过期不是发布集变小 |
| `scope-check` | 分支类别、受保护路径和每个角色的写集都在 `scripts/gate_config.json` 的 `scope` 段，按列表顺序匹配（agent 先）；repair/ 与 chore/ 不能单靠前缀授权，须开 PR 的人落在仓库 owner allowlist 上；chore 与 agent 同受受保护路径（`.cursor/` `.github/` `data/` `scripts/`、`README.md`、`LOOP.md`）；agent 分支 `cursor/t<N>-<role>-…` 只能写自己角色的写集，`{task}` 绑到分支名里的任务号（含 `-b`/`-c`）：worker → `tasks/TASK-N/results.json`、`sql/`、开放分析文件（`open_analysis.md` `manifest.json` `bootstrap.json` `decomposition.json` `run_worker.py` `STATUS.json`）及 `src/` `tests/`；verifier → `mine.json`、`mine_sql/`；auditor → `review/TASK-N/`、`RESULT.json`、`launches.json`、`backlog.md`；碰别的路径是 OUT，碰受保护路径是 DENY，角色在配置里没有写集直接红；任何 agent 都不得改任务书 `tasks/TASK-N.md`；diff 用 `--no-renames`，改名算一删一增，两边都判 |
| `history-audit` | 移动已有的栅不得与被它度量的东西同 PR，且正文须有 `BAR-CHANGE:` 并点名每个被移动的栅路径；被度量路径是 files 减去栅路径（闸门脚本 fail-site 净删算移动栅，但不自己锁自己）；`tasks/**/*.sql` 属被度量；任务书 fenced `numbers`/`fixture`/`frame`/`n`/`identities` 里放宽容差、删名字（identities：删一行、改写一行、放宽该行容差）或删整块算移动栅，收窄容差不算；**闸门本身是栅**：`scripts/`、`.github/` 下已有文件的任何字节改动，以及闸门脚本的测试（`tests/test_<闸门>*.py`、`tests/mutations/`、`tests/fixtures/`）的改动，都算移动栅——单独 PR、正文 `BAR-CHANGE:` 点名路径、不与被度量路径同 PR；fenced `outside_frame` 反过来：往里加名字（或新加这块）算移动栅，删名字不算；`scripts/gate_config.json`（闸门读的项目事实：表、键、两边文件名、数字族前缀、分支类别与角色写集）任何改动都算移动栅；死路径栅移入 `RETIRED` 块而非删除，live∪RETIRED 的 glob 丢失才算删栅 |
| `tests` | 有 `tests/test_*.py` 时跑 pytest |

前三个是 main 的必需检查。

## 仓库设置（不在脚本里，在 GitHub Settings 里）

闸门脚本管的是 PR 的内容；下面三样只能靠仓库设置，改了要在这里同步记一笔：

- **`.github/CODEOWNERS`**：`.github/**`、`scripts/**`、`tests/**`、`data/**`、`LOOP.md`、`README.md`、`.cursor/**`、`tasks/TASK-*.md` 归 owner。main 的分支规则开「Require review from Code Owners」，碰这些路径的 PR 没有 owner 审阅就合不进去。
- **main 的必需检查**：`tests`、`output-check`、`scope-check`、`history-audit` 四个都必需（`tests` 以前不是）。必需检查按 job 名对上，改 `ci.yml` 里的 job 名要同步改设置。
- **禁 force-push**：main 和 `cursor/**`、`box/**`、`chore/**`、`repair/**` 都不允许 force-push 和删除分支。「3 次改写」数的是留下来的 commit，force-push 抹掉旧版本就数不到（TASK-8、TASK-9 各推过三个 worker 版本，main 上每个输出文件只剩 1 个 commit）；identity 检查同理。

## 本地 `./verify`

一条命令，固定子命令，失败非零。调用现有脚本，不另写一套规则。

```
./verify              # 与 CI 相同：pytest、output-check、relations；PR 上再跑 scope-check 与 history-audit
./verify task 6       # 只跑 TASK-6 的 output-check 与 relations
./verify relations 6  # 只跑 TASK-6 的 double / permute / identities
./verify probe        # 已知必红的探针（常数 SQL、relations 写死分母、RESULT 假 out_of_turns、RESULT 假 success 超 16 启动、RESULT 假 out_of_budget 不足 16、TASK-N-b 改容差、开 -d）；仍绿则 ./verify 自身坏了
```

main 上不跑 scope-check / history-audit（与 CI 一致）。`./verify probe` 在丢弃用的树里跑探针，不以本仓库的绿灯当证据。

## output-check 实际做了什么

按顺序，任何一条不过就红。**在 pull request 上，下面 2–11 条只作用于这次 diff 碰到的任务**（`tasks/TASK-N.md` 或 `tasks/TASK-N/` 下任何文件，包括只改 `results.json` 或只改 `mine.json`）。没碰到的任务打一行 frozen summary，不把失败并进总账——`status: open` 且两边已经不合的任务（ITERATE）因此不能挡住一条无关的 PR。没有 `--base-ref` 时（main 上的 push）仍走完全部任务。任务书发现是顶层 glob `tasks/TASK-*.md`（非递归）。**若 `tasks/` 下任一 TASK-N 目录里有 `results.json` 或 `mine.json`，而对应的 `tasks/TASK-N.md` 不在该 glob 里，这一条对整棵树生效、不受 PR freeze 跳过**（plan §2.6）：把任务书移走不得让检查变成「nothing to check」绿灯。

1. `data/corpus_v2.sqlite` 的 sha256 与 `README.md` 里记的一致。语料不对，后面全部无意义。
2. 任务书有且只有一行 `status: open` / `closed` / `escalated` / `blocked`，`numbers` 块能解析。可选一行 `corpus_sha:`（64 位小写 hex，可带反引号）：收口时盖上当时 README 的语料 pin。可选的 fenced `n` 块、`frame` 块与 `identities` 块也在这里解析。`escalated` 与 `blocked` 暂停该任务第 3–9 条（重放、比对、声明 n、恒等式、改写计数）。**`status: closed` 且 stamp 缺失或与当前 README pin 不符 → STALE**：第 3–9 条不跑，不把失败并进总账，也不打印 `N/N number(s) agree`（plan §4.5）。顶层 glob 找不到任务书、但对应 TASK-N 目录里还有 `results.json` 或 `mine.json`：直接红，不走「nothing to check」。第 10 条（RESULT.json）与第 11 条（分叉身份）在终态任务上仍跑：STALE/suspended 的 RESULT 对不上机器事实同样红，改容差的 `TASK-N-b` 同样红。
3. 两个输出文件的每一行恰好是 `{name, value, n, query}`，名字集合与 `numbers` 块**相等**——少一个和多一个都红；同一文件内不得有重名，也不得有两个数字共用一条算路。算路按 `route()` 解析后的路径计（`sql/../sql/x.sql` 与 `sql/x.sql` 是同一条），不是按 query 字符串。若有 `n` 块，其名字集合必须与 `numbers` 相等；每一行是非负整数常数或 `derived:` 表达式。
4. 每个 `query` 是下面两种之一：
   - `tasks/TASK-N/<…>.sql`：一条语句，`SELECT` 或 `WITH` 开头，返回恰好一行一列；`EXPLAIN QUERY PLAN` 必须出现对语料表 `videos` / `windows` / `syllables` / `runs` 的 `SCAN` 或 `SEARCH`（`SELECT 12345` 过不了这一关）；同一条语句执行两次结果必须相同；`strip_and_split` 之后不得出现 `random()`、`randomblob()`、`strftime('now')` 族；
   - `derived:<expr>`：只用其他已声明的数字名、数字、`+ - * /` 和括号。表达式至少要引用一个已声明的数字名——`derived: 567` 这种常数不是算路，直接红。
5. 同一个 `.sql` 文件不得同时出现在两个文件里；`strip_and_split` 之后的语句文本 sha256 两边也不得相交（把 `sql/` 拷进 `mine_sql/` 过不了这一关）。定义可以共享，**实现不行**。`derived:` 允许两边写成一样，因为它的每个输入都各自被重放过。
6. 每个数字都等于它自己那条算路跑出来的结果，误差在容差内。`derived:` 用的是**重放出来的**值，不是 agent 自己写下的值——所以「把输入写错、再把推导写成与错输入自洽」这条路是走不通的，两行都会红。
7. 两套数字每个 `value` 在容差内相等，每个 `n` 完全相等。不一致的把两个数都打出来。只两边 `n` 相等不够（plan §2.5）：若有 `n` 块，每个写下的 `n` 还必须等于声明的常数或 `derived:`（代入的是重放值）。两道检查一起做。没有 `n` 块时，声明 n 那一道不激活。若有 `identities` 块，每一行 `<expr> = <expr>  <tol>` 用重放值求；只在**该文件**里每个数字名都是 SQL 算路时才计，否则跳过（不合并两边的字典）。一条恒等式在 worker 与 verifier 两边都被跳过（两边都把其中某个名字写成 `derived:`）就等于从没检查过：`open` 的任务直接红，规则落地前已 `closed` 的任务只打印一行 `closed before this rule, not failed`。期间恒等式 `n_videos_pre + n_videos_post + n_unassigned_period = frame.videos_expected` 不再是脚本里的特例：它就是每份任务书 ```identities``` 块里的一行，按上面同一规则求。
8. 动过同一个输出文件的 commit 不超过三个，从该任务书最近一次改动那个 reset commit 计起。`escalated` / `blocked` 不计。
9. 引入某一边文件的那个 commit，它自己的树和**所有祖先**的树里都没有另一边的文件。两边的引入 commit 不能有祖先关系，必须来自不同分支、身份不同（plan §2.7）。身份 = author 加 committer：author 是提交方自己填的，改一行 `--author` 就能换（TASK-9 worker `ac1ee4f` 就是这样过的旧检查），所以两边只在 author 上不同、committer 相同时闸门会打印一句，但不红——两个 Cursor Cloud Agent 的 committer 本来就同一个。CI 能证明的是「两边没有从对方的树出发」，证明不了「是两个不同的 agent 算的」；后者靠 fyp 记的启动账本和模型家族分配。只看引入 commit 自己那一棵树，挡不住「先提交自己的、再 merge 对方」或同一条分支上分三次写出两边。
    - **一边不换手**：open 任务里，PR 中每个动到 `results.json` 或 `mine.json` 的 commit 都要与该边引入 commit 同一身份（author 和 committer）。merge commit 里改了输出文件也算动到。force-push 抹掉的历史 CI 看不见，要靠分支保护禁 force-push（阶段 0 第 6 项）。
    - **已关闭任务冻结**：任务书在 base 和 head 上都是 `closed`，PR 就不得改 `tasks/TASK-N/` 下任何文件（两边输出、SQL、RESULT、账本都算）。要改就先在任务书上把 `status` 改回 `open`，同一个 PR 里改也行，但任务书是 owner 的文件，agent 分支做不到。`4918765` 那种关闭之后再改两边输出的情况以后直接红。
10. 若 `tasks/TASK-N/RESULT.json` 存在于 `closed` / `escalated` / `blocked` 任务，按 schema 核对：`subtype` 与 `verdict` 独立，后者只在 `subtype: success` 时非空；`success` 要求两边齐、数字在容差内一致、live closed；`out_of_turns` 要求改写次数已到上限 3；`corpus_sha` 必须等于任务书的 `corpus_sha:` stamp（任务书没 stamp 时对当前 README pin）。`turns_used` 必须等于该任务 `tasks/TASK-N/launches.json` 的记录数（每条 `{id, role, at}`）；根任务与 `-b`/`-c` 的账本长度之和是这一轮家族的启动次数，上限 16。`subtype` 不是 `out_of_budget` / `blocked` 而家族合计 `> 16` → 红（已有子任务书的父 RESULT 不再按后来的家族增长重判（父 RESULT 分叉后不可改），但父任务自己的账本已经 `> 16` 仍红）；`subtype: out_of_budget` 而家族合计 `< 16` → 红。账本由 coordinator / auditor 追加（记下 worker / verifier / auditor / repair 启动），worker / verifier 不得自造启动记录。本 PR 新收成终态的任务必须有 RESULT（因而也必须有账本）；落地前已关闭的任务可以没有。存在于 `open` 则红。没有 `cost_usd` / `budget_usd` / `val_iterations`。根任务 `forked_from` 为 null、`fork_depth` 为 0；字母后缀任务必须是父 id 与父 depth+1，且 `fork_depth ≤ 2`。
11. 若存在 `tasks/TASK-N-b.md`（深度 2 为 `-c`）：```numbers``` 与 ```n``` 围栏（以及父任务书上已有的 ```frame``` / ```identities```）必须与直接父任务书**字节级相同**——改一个容差就红，那是新任务，不是分叉。子任务书必须有 `## Prior Attempts`（父假说、verdict 或 `out_of_turns` 的 subtype、why、父 RESULT 的关键数字）。父任务保持 `closed` 或 `escalated`，父 `RESULT.json` 在子任务书加入之后不得改、不得删。父 RESULT 须为 `verdict: refuted` 或 `subtype: out_of_turns`。开 `-d`（第三次分叉）红，应把该轮标 `blocked` 而不是再开一份任务书。无输出的子任务书也跑这一条。Bot 的 `check-brief` 不在本仓库，不顶替这一关。

同一 job 里、在 `/tmp/gate/output_check.py`（PR）或 `scripts/output_check.py`（main）之后，另跑 `python scripts/relations.py`。这一步读的是 **HEAD 工作树**，不是 `/tmp/gate`：A1 之后 PR 上的闸门脚本是 base 的拷贝，新加的 `relations.py` 在合入之前 base 看不见。临时语料只写 `$RUNNER_TEMP`（或本地 tempfile），跑完删除，**从不写进 `data/`**。它不做 PR freeze。数字来自重放，不来自 agent 写下的值。除 double / permute 外还跑 **exclude**（按 ```frame``` 谓词删掉不发布的行再重放，仅在 `frame` 有 `published_expected` 时）和 **anchor**（`published_expected` 必须等于排除后单位表的行数）；按定义读 frame 之外的行的名字写进任务书 ```outside_frame``` 块豁免 exclude，往这块加名字是 history-audit 的移动栅。

闸门脚本本身不写这个项目的任何事实：表名、主键/外键、要加前缀的类型列、单位表、两边输出文件名、语料路径、pin 文件、数字族的前缀（`n_` 是 count，`agree_`/`rare_share_`/`gap_`/`did_`/`rate_*_pm` 是 rate）、分支类别、受保护路径和每个角色的写集都在 `scripts/gate_config.json`。PR 上 CI 把 base 分支的这份配置和三份闸门脚本一起拷进 `/tmp/gate`，所以 PR 改不了自己被判的规则；`relations.py` 从 HEAD 跑，读的是 HEAD 的配置，这是已知缺口，与「PR 自己的 ci.yml 定义 job」同一类。换一个项目改配置不改脚本。

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

分支本身就是断点：哪些 commit 在，就说明做到哪一步了。任务书上的 `status` 仍是控制开关。`RESULT.json` 是 auditor 在收口时留下的结构化结局，不替代 `status`，也不由 worker/verifier 写。

## 收口

`worker` 与 `verifier` 都合入、`output-check` 报出全部一致之后，把任务书改成
`status: closed`，并写一行 `corpus_sha:`，值为当时 `README.md` 里的语料
sha256——这一步自己也要过 `output-check`，所以两边没齐或有一个数字不一致
时，改不动。stamp 与当前 pin 一致的关闭任务仍会重放；不一致或缺失则标
**STALE**，跳过重放，不参与红绿，**不打印** `N/N number(s) agree`。

keep rate 抄的是 live closed 任务那一行 `N/N number(s) agree`。STALE 不是
39/39，不得把 STALE 跳过当成留下了全部数字。

然后放 `auditor`：读这批 commit 的 patch 与每个 PR 的正文，答六个固定问题，每条结论带
commit sha、文件、行号，给不出就写 UNKNOWN。它写 `review/TASK-N/audit.md` 与
`tasks/TASK-N/RESULT.json`，不得改任何代码、测试、声明或栅。

它的结论**只进 `backlog.md`**，永远不直接变成下一个任务的题目。否则这台专门生产过程
缺陷的机器会一直吃掉轮次。

收口时在 `backlog.md` 记一行 keep rate：这个任务产出了几个数字，留下了几个。连续低于
一半，下一个任务不派 agent，自己做。数字来自 live closed 的 `N/N agree`，不是 STALE。

## 轮次结果 `RESULT.json`

`auditor` 在任务停止时写 `tasks/TASK-N/RESULT.json`。`worker` 与 `verifier` 不写这份文件。

`subtype` 是机器结局，`verdict` 是研究判断，二者独立。`subtype: success` 只表示两边齐、数字在容差内一致、CI 事实与「跑完了」相符；**不**表示假说成立。假说是否成立只看 `verdict`：`supported` / `refuted` / `inconclusive`。只有 `subtype` 为 `success` 时 `verdict` 才非空，否则必须是 `null`。

`subtype` 取值：`success`、`out_of_turns`、`out_of_budget`、`blocked`、`infra_failure`、`stale`。没有 `cost_usd` / `budget_usd` / `val_iterations`。`turns_used` 是本任务 Cloud Agent 启动次数，必须等于 `tasks/TASK-N/launches.json` 的 `len`；`turn_cap` 仍是本轮改写上限 3。家族（父任务 + `-b` + `-c`）合计启动次数上限 **16**。碰到上限 → `subtype: out_of_budget`，停下来报告 Tom，agent 不得自行继续。

`forked_from` 与 `fork_depth` 由分叉规则钉死，见下一节。

## 启动账本 `launches.json`

git 推不出 Cursor 启动次数，所以仓库里必须有一份可核对的账本。`output-check` 读的是文件，不是美元。

- 路径：每个任务一份 `tasks/TASK-N/launches.json`（分叉各自一份；家族合计把父、`-b`、`-c` 的长度加起来）。
- 形状：`[{id, role, at}, …]`。`id` 在该文件内唯一；`role` 为 `worker` / `verifier` / `auditor` / `repair` / `coordinator`；`at` 非空字符串（时间戳或启动 id）。
- **谁写**：coordinator 或 auditor 追加（把 worker / verifier / auditor / repair 等启动记进去）。worker / verifier 不得自己编账本。
- **规则**：`RESULT.turns_used == len(该任务账本)`。家族合计 `> 16` 且 subtype 不是 `out_of_budget` / `blocked` → 红。`subtype: out_of_budget` 且家族合计 `< 16` → 红。
- 落地前已关闭、没有 RESULT 的任务（TASK-6）不必补账本，也不发明研究 verdict。本闸门之后新收成终态的任务，RESULT 与账本一起要有。

同一语料 pin 上关了几道题，记在 `backlog.md`，不进 RESULT，也不叫 `val_iterations`。

本闸门落地前已经 `closed` 的任务可以没有 `RESULT.json`。文件一旦存在，或本 PR 把任务书从非终态收成 `closed` / `escalated` / `blocked`，`output-check` 按上面核对，对不上就红。

## 分叉（同一测量目标，只换假说）

一轮以 `verdict: refuted` 或 `subtype: out_of_turns` 结束时，可以开一份兄弟任务书 `tasks/TASK-N-b.md`（再一次是 `-c`）。测量目标不变，只换假说。`output-check` 执行下面的规则；Grok Bot 的 `check-brief` 在仓库外，不顶替。

边界（最重要）：

> 同一份 `numbers` + 容差（```numbers``` / ```n``` 围栏字节级相同）→ 自动分叉，不必问 Tom。
> 改 `numbers` 或容差 → 新任务，等 Tom。不是分叉。

触发时：

1. 建 `tasks/TASK-N-b.md`（字母后缀；深度 1 = `b`，深度 2 = `c`）。
2. ```numbers``` 与 ```n``` 围栏（含其中的容差）必须与父任务书 `TASK-N.md`（或上一封信）**字节级相同**。父任务书上的 ```frame``` / ```identities``` 同样不得改——那些会重定义测量集。
3. 加 `## Prior Attempts`：父假说、verdict（若是 `out_of_turns` 则记 subtype）、`why` 一行、父 RESULT 的关键数字。
4. 只有假说 / 叙述可以改，不得改 numbers / n / 容差 / 测量集身份。
5. 父 `TASK-N` 保持终态（`closed` 或 `out_of_turns` 时的 `escalated`），不重开；父 `RESULT.json` 不得改、不得删。
6. 子 RESULT：`forked_from` = 父任务 id（`TASK-N` 或 `TASK-N-b`）；`fork_depth` = 父 depth + 1（父为 null/0 则子为 1）。
7. **`fork_depth ≤ 2`**。第三次分叉必须变成 `blocked`（写进任务书，检查拦住），不得开 `-d`。

本仓库不发明一份活的 `TASK-6-b`；规则用 `tests/` 夹具与 `./verify probe` 钉死。

## 语料更换

语料变动走 `repair/` PR（agent 碰不了 `data/` 与 `README.md`）：把新语料放到配置里的路径，跑 `python scripts/repin.py`，它只改 `README.md` 那一行 sha256 pin，并列出哪些 `status: closed` 任务书会变成 STALE。**同一条 PR**里提交语料和 pin，别的不动。

- 关闭任务书上的 `corpus_sha:` 是收口时的语料，**不改**。stamp 与新 pin 不符 → 该任务 STALE：跳过重放，不红，不打 N/N agree。
- `RESULT.json` 的 `corpus_sha` 必须等于**任务书的 stamp**（任务书没 stamp 时才对 README pin）。它记录的是这些数字在哪份语料上算出来的，不随 re-pin 改写；改写成没跑过的语料直接红。
- 已关闭任务在 base 与 head 上都 `closed` 时 `tasks/TASK-N/` 下什么都不能改（冻结），所以 re-pin 的 PR 本来也碰不到 RESULT。
- 要让某个关闭任务在新语料上重新活过来：`chore/` 把它改回 `status: open`，重新跑一轮，收口时盖新 stamp、写新 RESULT。「两边写下的值彼此相等」不算数，重放对的是新语料。
