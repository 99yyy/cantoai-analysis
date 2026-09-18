# ROUND-5：拆掉 expected/ 同义反复，声明对真语料

## 元数据

- 阶段：0（立题；第 1 波 impl 任务待 Tom 写入本文件后再进阶段 1）
- backlog 条目：#13 契约强制校验 corpus sha256；拆 `expected/` 同义反复
- 执行角色：Cloud Agent（阶段 2 盲配对 impl_a/impl_b + tests；阶段 4 review）；**音频员本轮不跑推断**
- 方法审打回计数：0/2
- 复核打回计数：0/2
- Cloud Agent launch 次数：0（预算见 yaml）
- 预测仓库：`https://github.com/99yyy/cantoai-analysis`
- 预测 commit：（方法审通过且规格合入后填入；必须早于任何结果 commit）
- 结果 commit：
- 契约：`.cursor/rules/analysis-contract.mdc` 英文 v3；合并判据含 `tests` / `contract-check` / `scope-check` / `history-audit`（PR #30）

## 问题（一句话，可被数据/CI 否定）

去掉（或削弱）`expected/` 对 `frame.yaml` / ROUND yaml 的镜像式同义反复之后，声明的行数、sha256、baseline 等是否仍能被 **对 `data/corpus_v2.sqlite`（及真实输入文件）的检查** 证伪或通过——而不是只在 `expected/` 与声明之间互抄？

## 假设

1. **H1**：`data/corpus_v2.sqlite` 的 sha256 可被 CI 强制等于 `frame.yaml: inputs.corpus_sha256`；缺文件、改字节或改 frame 而不改对方时检查为红。
2. **H2**：凡今日仅靠 `expected/*` 与声明文件互相对齐的条目，可改为（或附加）对真语料 / 真 CSV 的可失败查询；仅改 `expected/` 迎合观测值而不改代码时，`history-audit` 或新规则能拦住或要求 `BAR-CHANGE:`。
3. **H3**：在 ROUND-4 已堵住的 `expected_rows` 旁路之上，本轮不削弱 gate；`pd.merge(` 仍一处；无新的布尔关闭参数。

## 预测（冻结于方法审通过后的规格 commit）

1. 若 H1：存在名为 `corpus_sha256_matches_frame`（或等价）的检查，对损坏的 corpus 或错误的 frame hash 为 FAIL；反例测试能杀死缺失实现。
2. 若 H2：至少一条原 `expected/` 镜像检查改为读语料（或明确删除该镜像并在 `BAR-CHANGE:` 说明）；`tests/mutations/` 有对应变异体被杀死。
3. 若 H3：ROUND-4 的旁路回归测试仍绿；本轮不重跑 ROUND-3 metrics。

## 判据

- 合并：`tests`、`contract-check`、`scope-check`、`history-audit` 全绿（不读 PR 正文/diff）。
- 改栅（已存在的 `expected/` 值、`frame.yaml` / ROUND yaml 的 expected_rows / tol / threshold / min_judgeable / B / baseline_model、mutations 减少、反例减少、contract_check 条数减少）：**不得与** `src/` `sql/` `data/` `scripts/` 同 PR；正文须有 `BAR-CHANGE: <理由>`。
- 分支前缀：`cursor/r5-<scope>-` / `chore/` / `repair/`（见 LOOP / #30）。

## 数据

- 范围：仓库内 `data/corpus_v2.sqlite`（相对路径）；绝对路径按契约为红。
- ROUND-3/4 metrics 不重算；ROUND-4 旁路结论保留；ROUND-4「sha256 钉死」已更正为未强制。

## 工具

- 不重跑音频模型推断。
- **第 1 波 impl 任务：待 Tom 写入本节。**（题目已定：拆 `expected/` 同义反复 → 声明对真语料；含 corpus sha256 强制校验。）

## 脚本契约

- `impl_a` / `impl_b`：只写 `src/`、`sql/`、`frame.yaml`（若 Tom 指定改 `scripts/contract_check.py`，则改走 `repair/` 或由 Tom 另开，不混进 cursor/r5-impl_*）。
- `tests`：只写 `tests/`，不得读/改 `src/`。
- `review`：只写 `review/ROUND-5/result.md` 与 `review/ROUND-5/recompute/`。

## 阶段顺序

- 阶段 0：本文件 + `rounds/ROUND-5.yaml` 经 `chore/` PR 合入。
- 阶段 1：Tom 补全第 1 波任务后，派审稿员方法审（或 v2.1 三 mandate）。
- 阶段 2 第 1 波：同时 launch `impl_a` + `impl_b` + `tests`；tests 先合；两份 impl 先绿者合。
- 无 comparison 波（除非 Tom 在 yaml 中追加）。
- 阶段 4–5：review → 裁决。

## 预算

- 消息：12
- launch：见 yaml `launch_budget`
- 执行：12 小时

## 停止条件

- 仓库根 `STOP`
- 方法审两次打回
- 任一 scope 第二次 launch 仍失败

## 争议记录

- ROUND-4 曾误称 sha256 已钉死；已更正并开本轮。

