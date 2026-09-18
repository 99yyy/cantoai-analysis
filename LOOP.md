# CantoAI 自主研究回路（LOOP，v2：Cloud Agent 并发版）

状态以本仓库文件为准；聊天与文件冲突时以文件为准。小 jerry 不入群。

v2 改了什么、为什么：ROUND-3 暴露了三个 v1 结构性缺口。（1）Cloud Agent 的机器里没有语料，所有碰数据的契约检查都退化成同义反复（`expected/` 是 `frame.yaml` 的镜像）。（2）分析员从共享机器直接推 main，没有任何机器闸门，结果 7fe0ccf 在产出正确数字的同一个 commit 里给 `checked_merge` 加了 `enforce_expected=False` 和一个「无 expected_rows 门」的 `left_attach`——契约第 9 条被掏空，无人察觉。（3）一轮里 Cloud Agent 只被允许启动两次、只写脚本，而它恰恰是唯一一个**由机器隔离保证独立性**的执行者。v2 的原则：语料进仓库；除 Tom 外没人直接推 main；独立性靠隔离的 VM 而不是靠约定；并发只在共享声明合入之后展开。

## 一轮 = 一个可证伪的问题

| 阶段 | 谁 | 做什么 |
|------|-----|--------|
| 0 立题 | fyp | 写 `rounds/ROUND-N.md` + `rounds/ROUND-N.yaml`（comparisons、write_scopes、waves）；经 PR 合入 |
| 1 方法审 | 审稿员 | 跑之前审：工具是否适用、判据能否重算、预测是否已写死、write_scopes 是否两两不相交；写 `review/ROUND-N/method.md`，经 PR 合入 |
| 2 代码 | Cloud Agent ×2，**盲配对** | `impl` 只写 `src/ sql/ frame.yaml`；`tests` 只写 `tests/`，且**看不到** impl 的分支，只看规格。两者并发，各自开 PR。tests 的 PR 先合，impl 的 PR 必须在 tests 合入后 rebase 通过 CI 才能合 |
| 3 执行 | Cloud Agent ×m（非音频）/ 音频员（音频） | 阶段 2 全部合入后，**每个 `comparison_id` 一个 agent**，从同一个 main commit 出发，只写 `ROUND-N/<comparison_id>/`；音频推断留在共享机器，走 `box/rN-audio-…` 分支开 PR |
| 4 复核 | Cloud Agent ×1 | 独立重算：只写 `review/ROUND-N/`，禁止 `import src`；从 `data/` 和 `ROUND-N/*/metrics` 用自己的最小 SQL/pandas 重算每个关键数字；写 `review/ROUND-N/result.md`，结论只有「通过」或「打回 + 可验证条件」 |
| 5 裁决 | fyp | 只读 CI 状态与 `review/ROUND-N/result.md`；写 `RESEARCH_LOG.md`，取下一题；经 PR 合入 |

一轮只回答 ROUND-N.md 里的那一个问题。顺便发现的东西只进 `backlog.md`。

## 两波启动（硬顺序）

- **第 1 波**（阶段 2）：同时启动 `impl` 和 `tests` 两个 agent。两个 prompt 只含规格路径，不含对方的分支。tests 的 PR 合入后，impl 的分支必须包含 tests 的提交并通过 CI；CI 里 `mutations_killed` 用的是 tests 写的测试，所以 impl 无法给自己写「恰好通过」的测试。
- **第 2 波**（阶段 3 + 4）：第 1 波全部合入 main 后才启动。m 个 comparison agent 与 1 个复核 agent 同时启动，prompt 里写死出发 commit（`git rev-parse HEAD` 必须等于该值，否则先 `git checkout`）。复核 agent 只有在 m 个 comparison PR 全部合入后才启动——它读的是合入后的 `ROUND-N/*/metrics`。
- 并发上限 **6**（Pro 档实测 8；Pro+ 官方只说「明显更高」，未公布数字）。超过 6 个 comparison 就分两批。
- 每轮 launch 预算：2 + m + 1，另加 **2** 次重试。任何 scope 只允许重启一次；第二次失败写进 ROUND 争议记录并升级 Tom。

## 写入范围（机器隔离，不靠自觉）

- 每个 agent 的分支必须命名为 `cursor/r<N>-<scope_id>-…`；共享机器上的音频分支为 `box/r<N>-audio-…`。
- `rounds/ROUND-N.yaml: write_scopes.<scope_id>` 列出该 scope 允许改动的 glob；CI 的 `scope-check` 对比 PR 的改动文件，越界即红。
- `impl`、`tests`、各 `comparison_id`、`review` 的 write_scopes **两两不相交**；方法审在阶段 1 检查这一点。
- 没有任何 scope 包含 `.cursor/`、`.github/`、`fixtures/schema.sqlite`、`fixtures/manifest.schema.json`、`data/`、`rounds/`。这些只由 Tom 改，或由 fyp 在阶段 0/5 经 PR 改 `rounds/`。

## 合并闸门（fyp 不读 diff，不读 PR 正文）

- main 有分支保护：必须通过 `tests`、`contract-check`、`scope-check` 三个检查，必须经 PR，**任何人不能绕过**（包括 Tom 的账号——bot 用的就是这个账号）。`STOP` 文件因此也走 PR，或由 Tom 临时关保护。
- fyp 合并的唯一判据：三个检查全绿。红了就不合。PR 正文、checks.json 的提交副本、agent 的自述，一律不算证据；CI 在 runner 里重新生成 checks.json。
- 红了怎么办：对该 agent 发**一次** follow-up（内容只有 CI 失败的日志路径），仍红则关闭 PR、记录、按预算重启一次。不在 PR 里讨论。
- 合并只用普通 merge。禁止 rebase 改写已推送历史、禁止 force-push、禁止碰数据集仓库；这三条一律拒绝并问 Tom。

## 数据

- 语料固定为 `data/corpus_v2.sqlite`，sha256 `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f`（与 ROUND-3 manifest 一致，与 Tom 本机副本一致）。`frame.yaml: inputs` 记录该 sha256，`contract_check` 逐次比对。
- 所有 Cloud Agent 用 `--corpus-path data/corpus_v2.sqlite`（相对路径）。绝对路径按契约第 18 条为红。
- 音频文件不进仓库；需要音频的工作留在共享机器。

## 派单与消息

- 派单 **1:1**，只发路径 + 阶段号。群「CantoAI 研究」每轮 ≤ 3 条里程碑。
- 每轮 bot 间消息上限 **12**。v2 把阶段 3（非音频）和阶段 4 搬到了 Cloud Agent，所以正常一轮的 bot 消息应当只剩：阶段 1 派单与回稿（2）、里程碑（≤3）。
- `CloudAgent.launch` 完成后会唤醒 fyp（ROUND-1、ROUND-2 已各验证一次）。90 分钟没有唤醒也没有 PR，视为该 launch 失败，按预算重启一次。不建轮询例程。
- 每次醒来先查仓库根目录 `STOP`。

## 打回与升级

- 打回必须是可验证通过条件（路径 + 命令，或「某文件某键等于某值」）；写不成的标 `advisory`。计数写在 ROUND 文件，第 3 次升级 Tom。
- 升级触发与六项格式同 v1：打回第 3 次；两方各执一词且各有数字；需 GPU/付费/超 2 GB 权重；单次 >12h 或连续失败 2 次；周额度用尽；backlog 空；任何碰数据集仓库/改历史/force-push。
- 与上一轮结论矛盾不自动停，先在 `RESEARCH_LOG.md` 写「矛盾」节。

## launch prompt 模板（fyp 只填空，不改句子）

每个模板的第一行都是分支名要求，最后一行都是退出条件。`<…>` 为填空。

**impl**
```
Branch name must begin with cursor/r<N>-impl-. Read rounds/ROUND-<N>.md, rounds/ROUND-<N>.yaml, frame.yaml and .cursor/rules/analysis-contract.mdc. Implement the analysis for every comparison_id declared in rounds/ROUND-<N>.yaml. Write only under src/, sql/, and frame.yaml. Do not write tests. Do not run the analysis on data/; run only the fixtures. Open a PR whose body is exactly the output of: python scripts/contract_check.py --repo-root . --schema-sqlite fixtures/schema.sqlite --checks-file checks.json --frame-file frame.yaml --round-yaml rounds/ROUND-<N>.yaml
```

**tests**
```
Branch name must begin with cursor/r<N>-tests-. Read rounds/ROUND-<N>.md, rounds/ROUND-<N>.yaml, frame.yaml and .cursor/rules/analysis-contract.mdc. You are the adversary: from the specification alone, write tests/ and tests/mutations/ that a correct implementation must pass and an implementation with any defect listed in the contract must fail. Every assertion message named in the specification gets a pytest.raises with a ^-anchored match. Write only under tests/. Do not read or modify src/. Open a PR whose body is exactly the output of: pytest -q --collect-only
```

**comparison**（每个 comparison_id 一个）
```
Branch name must begin with cursor/r<N>-<comparison_id>-. Start from commit <sha>: run git rev-parse HEAD and check out <sha> if it differs. Run the analysis for comparison_id <comparison_id> only, with --corpus-path data/corpus_v2.sqlite and --out-dir ROUND-<N>/<comparison_id>/. Write only under ROUND-<N>/<comparison_id>/. Do not modify src/, sql/, frame.yaml or tests/. If the code cannot run, write BLOCKED in the PR body and stop; do not patch the code. Open a PR whose body is exactly the contents of ROUND-<N>/<comparison_id>/STATUS.json
```

**review**
```
Branch name must begin with cursor/r<N>-review-. Start from commit <sha>. Recompute every number in ROUND-<N>/*/metrics/*.json from data/corpus_v2.sqlite with your own minimal SQL or pandas. You may not import anything under src/. Write only under review/ROUND-<N>/. For each number write: the value you got, the value in metrics, and the command that reproduces yours. Verdict is either PASS or RETURN with one verifiable pass condition per item (path plus command, or file key equals value). Never write "not supported". Open a PR whose body is exactly the verdict line.
```

## ROUND-3 的后记（记录，不重跑）

ROUND-3 的三个 metrics 与 manifest 内部一致（BH 校正复算正确；语料 sha256 与 Tom 本机一致；row_accounting 里两次 `left_attach` 均 100% 匹配，未丢行），结论保留。过程缺陷两条，记入 RESEARCH_LOG：阶段 3 直接推 main、无 CI；`src/merge.py` 在同一 commit 里加了绕过 expected_rows 的路径。**ROUND-4 第 1 波的 impl 任务固定为**：删除 `enforce_expected` 参数；`left_attach` 必须从 `frame.yaml: joins` 取匹配行数字面量；`contract_check` 新增：`src/merge.py` 里 `pd.merge(` 恰好一处、任何 gate 函数不得有布尔关闭参数、`review/` 下不得 `import src`、`data/corpus_v2.sqlite` 的 sha256 等于 `frame.yaml: inputs` 所记。tests agent 对这四条盲写反例。

## 例程

- `cantoai-analysis PR 事件`（pr-opened / pr-merged，限本仓库）保留。
- `STATUS 看护 4h` 只对音频员的长任务有效；Cloud Agent 的完成靠 launch 唤醒。
