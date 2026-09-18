# CantoAI 自主研究回路（LOOP，v2.1：Cloud Agent 并发版）

状态以本仓库文件为准；聊天与文件冲突时以文件为准。小 jerry 不入群。仓库布局与写入者见 `LAYOUT.md`。

v2 改了什么、为什么：ROUND-3 暴露了三个 v1 结构性缺口。（1）Cloud Agent 的机器里没有语料，所有碰数据的契约检查都退化成同义反复（`expected/` 是 `frame.yaml` 的镜像）。（2）分析员从共享机器直接推 main，没有任何机器闸门，结果 7fe0ccf 在产出正确数字的同一个 commit 里给 `checked_merge` 加了 `enforce_expected=False` 和一个「无 expected_rows 门」的 `left_attach`——契约第 9 条被掏空，无人察觉。（3）一轮里 Cloud Agent 只被允许启动两次、只写脚本，而它恰恰是唯一一个**由机器隔离保证独立性**的执行者。v2 的原则：语料进仓库；除 Tom 外没人直接推 main；独立性靠隔离的 VM 而不是靠约定；并发只在共享声明合入之后展开。

## 一轮 = 一个可证伪的问题

| 阶段 | 谁 | 做什么 |
|------|-----|--------|
| 0 立题 | fyp | 写 `rounds/ROUND-N.md` + `rounds/ROUND-N.yaml`（comparisons、write_scopes、waves）；经 PR 合入 |
| 1 方法审 | Cloud Agent ×3，各审一个维度 | 跑之前审。`mr_falsify`：预测是否已写死、每条假设是否有能否定它的数据模式、阈值有无依据；`mr_tools`：工具在这批数据上是否适用、已知失效情形是否都写成了谓词、跨度是否一致；`mr_stats`：单位、聚类、基线、m、min_judgeable、组定义的来源。各写 `review/ROUND-N/method/<mandate>.md`，结论只有 PASS 或 RETURN + 可验证条件；三份全 PASS 才进阶段 2 |
| 2 代码 | Cloud Agent ×3，**盲配对 + 二选一** | `impl_a`、`impl_b` 同一 prompt 各写一份，只写 `src/ sql/ frame.yaml`；`tests` 只写 `tests/`，且**看不到** impl 的分支，只看规格。三者并发，各自开 PR。tests 的 PR 先合；两个 impl 都必须在 tests 合入后 Update branch 过 CI，**先绿的合，另一个关闭**；两个都红 → 规格有歧义，回阶段 0 |
| 3 执行 | Cloud Agent ×m（非音频）/ 音频员（音频） | 阶段 2 全部合入后，**每个 `comparison_id` 一个 agent**，从同一个 main commit 出发，只写 `ROUND-N/<comparison_id>/`；音频推断留在共享机器，走 `box/rN-audio-…` 分支开 PR |
| 4 复核 | Cloud Agent ×1 | 独立重算：只写 `review/ROUND-N/result.md` 与 `review/ROUND-N/recompute/`，禁止 `import src`；从 `data/` 和 `ROUND-N/*/metrics` 用自己的最小 SQL/pandas 重算每个关键数字；写 `review/ROUND-N/result.md`，结论只有「通过」或「打回 + 可验证条件」 |
| 4.5 行为审计 | Cloud Agent ×1 | 审的是这一轮**怎么做的**，不是数字对不对。读本轮全部合并 commit 的 patch 与 PR 正文，回答六个固定问题（是否有栅被挪动、是否有无检查支撑的断言、是否越界或未全绿即合、结论是否强于证据、声明的任务是否有未做即收口、哪些能变成机械检查）。每条结论必须带 commit sha + 文件 + 行；给不出就写 UNKNOWN。只写 `review/ROUND-N/audit.md`，不得改任何代码、测试、声明或栅 |
| 5 裁决 | fyp | 只读 CI 状态与 `review/ROUND-N/result.md`；写 `RESEARCH_LOG.md`，取下一题；经 PR 合入 |

一轮只回答 ROUND-N.md 里的那一个问题。顺便发现的东西只进 `backlog.md`。

## 分波启动（硬顺序）

- **第 0 波**（阶段 1）：三个方法审 agent 同时启动，各自只写一个 markdown。任何一份 RETURN，fyp 把三份的条件并集写回 `rounds/ROUND-N.md` 再来一次；两次仍 RETURN 升级 Tom。
- **第 1 波**（阶段 2）：同时启动 `impl_a`、`impl_b` 和 `tests` 三个 agent。三个 prompt 只含规格路径，不含彼此的分支。tests 的 PR 合入后，impl 的分支必须包含 tests 的提交并通过 CI；CI 里 `mutations_killed` 用的是 tests 写的测试，所以 impl 无法给自己写「恰好通过」的测试。
- **第 2 波**（阶段 3）与**第 3 波**（阶段 4）：第 1 波全部合入 main 后才启动。m 个 comparison agent 同时启动；复核 agent 只有在 m 个 comparison PR 全部合入后才启动——它读的是合入后的 `ROUND-N/*/metrics`。出发 commit 用 launch 工具的 `starting_ref` 钉死（fyp 把该 sha 写进 `rounds/ROUND-N.yaml: waves[].start_commit`），不靠 prompt 里让 agent 自己 checkout。
- **跨轮流水**：同一时刻最多**一轮**处于第 0 波或第 1 波（它们改 `src/`、`tests/`、`rounds/`），处于第 2 波及以后的轮数不限——第 2 波的 agent 从钉死的 commit 出发、复核 agent 不 import src，后续对 src 的改动碰不到它们。所以 ROUND-N 一进第 2 波，fyp 就可以开 ROUND-N+1 的第 0 波。
- 并发上限 **8**（Pro 档官方口径；Pro+ 只说「明显更高」，未公布数字，撞到上限的报错记进 ROUND 文件，之后按实测调）。超过就分批。
- 每轮 launch 预算：3 + 3 + m + 1 + 1（审计），另加 **2** 次重试。任何 scope 只允许重启一次；第二次失败写进 ROUND 争议记录并升级 Tom。
- 审稿员 bot 退出常规流程，只在 Cloud Agent 用量耗尽时顶替第 0 波；分析员只在 Cloud Agent 无法访问的输入（音频）上工作。

## 写入范围（机器隔离，不靠自觉）

- 分支必须属于四类之一，否则 `scope-check` 直接红：`cursor/r<N>-<scope_id>-…`（Cloud Agent）、`box/r<N>-<scope_id>-…`（共享机器）、`chore/…`（fyp 的声明与文档，只能改 `rounds/`、`RESEARCH_LOG.md`、`backlog.md`、顶层文档、`STOP`、`STATUS.json`）、`repair/…` 或 `cursor/repair-…`（Tom 指定的工具修复，免 scope 检查但在 git 历史里显式可见）。
- `rounds/ROUND-N.yaml: write_scopes.<scope_id>` 列出该 scope 允许改动的 glob；CI 的 `scope-check` 对比 PR 的改动文件，越界即红。
- `impl_a` 与 `impl_b` 共用同一 scope（二选一，只合一个）；其余 scope——`tests`、各 `comparison_id`、`review`、三个 `mr_*`——**两两不相交**；`mr_stats` 在阶段 1 检查这一点。方法审 agent 每个只准写一个文件 `review/ROUND-N/method/<mandate>.md`。
- 没有任何 scope 包含 `.cursor/`、`.github/`、`fixtures/schema.sqlite`、`fixtures/manifest.schema.json`、`data/`、`rounds/`。这些只由 Tom 改，或由 fyp 在阶段 0/5 经 PR 改 `rounds/`。

## 栅不得为了让检查变绿而移动

「栅」指决定某条检查通不通过的东西：`expected/` 里已存在的值、`frame.yaml` 或 `rounds/ROUND-N.yaml` 里已存在的 `expected_rows` / `expected_rows_tol` / `threshold` / `min_judgeable` / `B` / `baseline_model`、`tests/mutations/` 的补丁数、反例 `match=` 的条数、`scripts/contract_check.py` 发出的检查条数。

- 移动栅与改动它所度量的东西（`src/` `sql/` `data/` `scripts/`）**不得在同一个 PR 里**。
- 任何移动栅的 PR，正文必须有一行 `BAR-CHANGE: <理由>`。这行不使那次改动正确，它使那次改动对阶段 4.5 的审计可见——判断留给审计，不留给 CI。
- 为新代码**新增**一个栅不算移动，不会被拦。
- 以上由 CI 的 `history-audit` 机械执行。它在 2026-09-18 的一次真实事件之后加入：当时一个 commit 把三个已声明的期望值改成与空轮相符，观测值分毫未动，而它能通过是因为 scope-check 对不认识的分支名直接放行。

## 合并闸门（fyp 不读 diff，不读 PR 正文）

- main 有分支保护：必须通过 `tests`、`contract-check`、`scope-check`、`history-audit` 四个检查，必须经 PR，**任何人不能绕过**（包括 Tom 的账号——bot 用的就是这个账号）。`STOP` 文件因此也走 PR，或由 Tom 临时关保护。
- fyp 合并的唯一判据：四个检查全绿。红了就不合。PR 正文、checks.json 的提交副本、agent 的自述，一律不算证据；CI 在 runner 里重新生成 checks.json。
- 红了怎么办：对该 agent 发**一次** follow-up（内容只有 CI 失败的日志路径），仍红则关闭 PR、记录、按预算重启一次。不在 PR 里讨论。
- 合并只用普通 merge。禁止 rebase 改写已推送历史、禁止 force-push、禁止碰数据集仓库；这三条一律拒绝并问 Tom。

## 数据

- 语料固定为 `data/corpus_v2.sqlite`，sha256 `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f`（与 ROUND-3 manifest 一致，与 Tom 本机副本一致）。`frame.yaml: inputs` 记录该 sha256，`contract_check` 逐次比对。
- 所有 Cloud Agent 用 `--corpus-path data/corpus_v2.sqlite`（相对路径）。绝对路径按契约第 18 条为红。
- 音频文件不进仓库；需要音频的工作留在共享机器。

## 派单与消息

- 派单 **1:1**，只发路径 + 阶段号。群「CantoAI 研究」每轮 ≤ 3 条里程碑。
- 每轮 bot 间消息上限 **12**。v2 把阶段 1、3（非音频）、4 都搬到了 Cloud Agent，所以正常一轮的 bot 消息应当只剩里程碑（≤3）。
- `CloudAgent.launch` 完成后会唤醒 fyp（ROUND-1、ROUND-2 已各验证一次）。90 分钟没有唤醒也没有 PR，视为该 launch 失败，按预算重启一次。不建轮询例程。
- 每次醒来先查仓库根目录 `STOP`。

## 打回与升级

- 打回必须是可验证通过条件（路径 + 命令，或「某文件某键等于某值」）；写不成的标 `advisory`。计数写在 ROUND 文件，第 3 次升级 Tom。
- 升级触发与六项格式同 v1：打回第 3 次；两方各执一词且各有数字；需 GPU/付费/超 2 GB 权重；单次 >12h 或连续失败 2 次；周额度用尽；backlog 空；任何碰数据集仓库/改历史/force-push。
- 与上一轮结论矛盾不自动停，先在 `RESEARCH_LOG.md` 写「矛盾」节。

## launch prompt 模板（fyp 只填空，不改句子）

每个模板的第一行都是分支名要求，最后一行都是退出条件。`<…>` 为填空。launch 工具（`CloudAgent`，action=launch）没有分支名参数，分支靠 prompt 第一句约束；有 `starting_ref`（出发 commit）、`title`（写 scope id）、`model` / `model_params`（默认不传）；同一回合可连续调用多次以并发启动。PR 由 agent 自己在结束时打开。

**method review**（三个 mandate 各一份，`<mandate>` 取 falsify / tools / stats）
```
Branch name must begin with cursor/r<N>-mr_<mandate>-. Read rounds/ROUND-<N>.md, rounds/ROUND-<N>.yaml, frame.yaml, LAYOUT.md and .cursor/rules/analysis-contract.mdc. Do not read src/ or tests/. Review the round from one angle only, <mandate>: falsify = are the predictions frozen, does each hypothesis name a data pattern that would refute it, is every threshold justified; tools = is each tool applicable to this corpus, is every known failure mode written as a predicate, do measurement spans match; stats = unit, clustering, baseline, m, min_judgeable, and where each group definition comes from. Write exactly one file, review/ROUND-<N>/method/<mandate>.md, and nothing else. Verdict is PASS or RETURN; under RETURN list conditions each of which is a path plus a command, or a file key that must equal a value. Never write "not supported". Open a PR whose body is exactly the verdict line.
```

**impl**（`impl_a` 与 `impl_b` 各发一次，只有分支前缀不同）
```
Branch name must begin with cursor/r<N>-impl_<a|b>-. Read rounds/ROUND-<N>.md, rounds/ROUND-<N>.yaml, frame.yaml and .cursor/rules/analysis-contract.mdc. Implement the analysis for every comparison_id declared in rounds/ROUND-<N>.yaml. Write only under src/, sql/, and frame.yaml. Do not write tests. Do not run the analysis on data/; run only the fixtures. Open a PR whose body is exactly the output of: python scripts/contract_check.py --repo-root . --schema-sqlite fixtures/schema.sqlite --checks-file checks.json --frame-file frame.yaml --round-yaml rounds/ROUND-<N>.yaml
```

**tests**
```
Branch name must begin with cursor/r<N>-tests-. Read rounds/ROUND-<N>.md, rounds/ROUND-<N>.yaml, frame.yaml and .cursor/rules/analysis-contract.mdc. You are the adversary: from the specification alone, write tests/ and tests/mutations/ that a correct implementation must pass and an implementation with any defect listed in the contract must fail. Every assertion message named in the specification gets a pytest.raises with a ^-anchored match. Write only under tests/. Do not read or modify src/. Open a PR whose body is exactly the output of: pytest -q --collect-only
```

**comparison**（每个 comparison_id 一个）
```
Branch name must begin with cursor/r<N>-<comparison_id>-. Run the analysis for comparison_id <comparison_id> only, with --corpus-path data/corpus_v2.sqlite and --out-dir ROUND-<N>/<comparison_id>/. Write only under ROUND-<N>/<comparison_id>/. Do not modify src/, sql/, frame.yaml or tests/. If the code cannot run, write BLOCKED in the PR body and stop; do not patch the code. Write only the five files LAYOUT.md allows under that directory. Open a PR whose body is exactly the contents of ROUND-<N>/<comparison_id>/STATUS.json
```

**audit**（阶段 4.5，每轮一个）
```
Branch name must begin with cursor/r<N>-audit-. You are auditing how this round was carried out, not whether its numbers are right — a separate agent already recomputed those. Read LOOP.md, LAYOUT.md, .cursor/rules/analysis-contract.mdc, rounds/ROUND-<N>.md and rounds/ROUND-<N>.yaml. Then read the round's history: git log --merges --patch origin/main covering every commit after <start_sha>, and the body of every pull request merged in that range. Answer these six questions. Each answer is a verdict plus evidence: a commit sha, a file, and a line. An answer with no sha is not an answer; write UNKNOWN and say what you could not see. (1) Was any bar moved to make a check pass? A bar is a declared expected value, a tolerance, a threshold, a mutation patch, a counterexample pattern, or a check in scripts/contract_check.py. For every bar that changed, say what it was before, what it became, and whether the change came before or after a failing check on the same branch. (2) Did any claim in rounds/ROUND-<N>.md, RESEARCH_LOG.md or a PR body assert something no check verifies? For each such claim quote it and name the check that would have to exist. (3) Did any agent write outside its declared write scope, or did any branch merge without all required checks green? (4) Was any conclusion stated more strongly than its evidence? Compare each claim against the counts, the p-values and the ci_unreliable flags actually present in the metrics files. (5) Was anything in the round's declared task left undone while the round was closed as complete? Compare rounds/ROUND-<N>.md against what the merged diffs actually contain. (6) Which of the findings above can be turned into a mechanical check? For each, name the file it would live in and the exact condition. Propose nothing you cannot state as a condition. Write exactly one file, review/ROUND-<N>/audit.md, and nothing else. Do not modify any code, any test, any declaration, or any bar — if you believe a bar is wrong, say so under question 6 and stop. Verdict line at the top is CLEAN or FINDINGS: <n>. Never write "not supported". Open a PR whose body is exactly that verdict line.
```

**review**
```
Branch name must begin with cursor/r<N>-review-. Recompute every number in ROUND-<N>/*/metrics/*.json from data/corpus_v2.sqlite with your own minimal SQL or pandas. You may not import anything under src/. Read LAYOUT.md first. Write only review/ROUND-<N>/result.md and files under review/ROUND-<N>/recompute/; nothing else, anywhere. For each number write: the value you got, the value in metrics, and the command that reproduces yours. Verdict is either PASS or RETURN with one verifiable pass condition per item (path plus command, or file key equals value). Never write "not supported". Open a PR whose body is exactly the verdict line.
```

## ROUND-3 的后记（记录，不重跑）

ROUND-3 的三个 metrics 与 manifest 内部一致（BH 校正复算正确；语料 sha256 与 Tom 本机一致；row_accounting 里两次 `left_attach` 均 100% 匹配，未丢行），结论保留。过程缺陷两条，记入 RESEARCH_LOG：阶段 3 直接推 main、无 CI；`src/merge.py` 在同一 commit 里加了绕过 expected_rows 的路径。**ROUND-4 第 1 波的 impl 任务固定为**：删除 `enforce_expected` 参数；`left_attach` 必须从 `frame.yaml: joins` 取匹配行数字面量；`contract_check` 新增：`src/merge.py` 里 `pd.merge(` 恰好一处、任何 gate 函数不得有布尔关闭参数、`review/` 下不得 `import src`、`data/corpus_v2.sqlite` 的 sha256 等于 `frame.yaml: inputs` 所记。tests agent 对这四条盲写反例。

## 例程

- `cantoai-analysis PR 事件`（pr-opened / pr-merged，限本仓库）保留。
- `STATUS 看护 4h` 只对音频员的长任务有效；Cloud Agent 的完成靠 launch 唤醒。
