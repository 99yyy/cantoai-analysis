# ROUND-4：堵住 expected_rows 旁路，并钉死语料 sha256

## 元数据

- 阶段：2（wave1 进行中）
- backlog 条目：ROUND-3 后记 — 删 enforce_expected / left_attach 字面量 / contract_check 四条新规则
- 执行角色：Cloud Agent（阶段 2 盲配对 impl+tests；阶段 4 review）；**音频员本轮不跑推断**
- 方法审打回计数：1/2
- 复核打回计数：0/2
- Cloud Agent launch 次数：3（wave1 impl_a+impl_b+tests；预算见 yaml）
- 预测仓库：`https://github.com/99yyy/cantoai-analysis`
- 预测 commit：`d50e2dac57f39677fb98367ec600ea51c6600806`（方法审通过后冻结；必须早于任何结果 commit）
- 结果 commit：
- 契约：`.cursor/rules/analysis-contract.mdc` 英文 v3，sha256 `461e8928597b1269be05088f3296663b896f1a5c4d264c2d7be3cf41ad5db3e5`，commit `228c78a`

## 问题（一句话，可被数据/CI 否定）

删除 `enforce_expected`、强制 `left_attach` 只从 `frame.yaml: joins` 取匹配行数字面量，并让 `contract_check` 新增四条规则之后，这三个检查（tests / contract-check / scope-check）是否在 main 上全绿，且 `data/corpus_v2.sqlite` 的 sha256 与 `frame.yaml: inputs` 一致？

## 假设

1. **H1**：去掉 `enforce_expected` 布尔门后，任何绕过 `expected_rows` 的调用路径不复存在；`contract_check` 对「gate 函数不得有布尔关闭参数」为 PASS。
2. **H2**：`left_attach` / `pd.merge(` 在 `src/merge.py` 恰好一处，且匹配行数只读 `frame.yaml: joins.*.expected_rows` 字面量。
3. **H3**：`review/` 下不得 `import src`；`data/corpus_v2.sqlite` sha256 等于 `frame.yaml: inputs.corpus_sha256`。

## 预测（冻结于方法审通过后的规格 commit）

1. 若 H1–H3：CI `contract-check` 对下列检查均为 PASS：`merge_pd_merge_once`（或等价名）、`no_boolean_gate_bypass`、`review_no_import_src`、`corpus_sha256_matches_frame`（名称以 impl 落地为准，tests 反例必须能杀死缺失实现）。
2. 上述四条（`assertion_message_set`、`select_from_only_load_sql`、`no_measure_fillna_or_get_default`、`mutations_killed`）在当前 main 上已为 `PASS`；**impl 合入（且已 rebase 含 tests）后仍为 `PASS`**（不得因删除 `enforce_expected` / 改 `left_attach` 而转红）。
3. 本轮 **不** 重跑 ROUND-3 三个 comparison 的 metrics；ROUND-3 结论保留。

## 判据

- 合并唯一判据：PR 的 `tests`、`contract-check`、`scope-check` 三检查全绿（不读 PR 正文/diff）。
- `write_scopes` 两两不相交（阶段 1 方法审核）。
- 语料：`data/corpus_v2.sqlite`，sha256 `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f`。

## 数据

- 范围：仓库内 `data/corpus_v2.sqlite`（相对路径）；绝对路径按契约为红。
- ROUND-3 metrics 不重算；过程缺陷两条只记 `RESEARCH_LOG.md`。

## 工具

- 不重跑音频模型推断。
- 第 1 波任务（写死，见 LOOP.md「ROUND-3 的后记」）：
  1. 删除 `enforce_expected` 参数；
  2. `left_attach` 必须从 `frame.yaml: joins` 取匹配行数字面量；
  3. `contract_check` 新增四条：`src/merge.py` 里 `pd.merge(` 恰好一处；任何 gate 函数不得有布尔关闭参数；`review/` 下不得 `import src`；`data/corpus_v2.sqlite` 的 sha256 等于 `frame.yaml: inputs` 所记；
  4. tests agent 对这四条盲写反例（`tests/` + `tests/mutations/`）。

## 脚本契约

- `impl_a` / `impl_b` 只写 `src/`、`sql/`、`frame.yaml`（二选一合入）。
- tests 只写 `tests/`，不得读/改 `src/`。
- review（阶段 4）只写 `review/ROUND-4/`，禁止 `import src`。

## 阶段顺序

- 阶段 1：审稿员方法审（write_scopes 不相交、预测写死、四条规则可测）。
- 阶段 2 第 1 波（LOOP v2.1）：同时 launch `impl_a` + `impl_b` + `tests`（分支前缀 `cursor/r4-impl_a-` / `cursor/r4-impl_b-` / `cursor/r4-tests-`）；tests 先合；两份 impl Update branch 后先绿者合、另一关闭。
- 本轮无 comparison 波（不重跑 ROUND-3）。
- 阶段 4：review agent 核四条规则与 sha256；阶段 5 fyp 裁决。

## 预算

- 消息：12
- launch：wave1 的 2 + review 1 + 重试 2（见 yaml）
- 执行：12 小时

## 停止条件

- 仓库根 `STOP`
- 方法审两次打回
- 任一 scope 第二次 launch 仍失败

## 争议记录

- 阶段1 方法审打回 #1（审稿员）：预测第2条误写「当前 main 四条红、impl 后转绿」；contract-green 合入后四条已为 PASS。已按硬条件改写。

- 2026-09-18 进入阶段1方法审（#16/#13/#14 已合入 main）。

## 验证记录

- GitHub 例程是否触发：**是**（pr-merged PR #19，https://github.com/99yyy/cantoai-analysis/pull/19 ，分支 `chore/r4-pred2-baseline`，标题 docs(round-4): fix pred#2 baseline (PASS) + method reject 1/2；merge `8ede859`；CST 2026-09-18 ≈16:44）
- GitHub 例程是否触发：**是**（pr-merged PR #21，https://github.com/99yyy/cantoai-analysis/pull/21 ，分支 `chore/r4-method-pass`，标题 chore(round-4): method review — 通过 (re-review after #19)；merge `d50e2da`；CST 2026-09-18 ≈16:53）
- GitHub 例程是否触发：**是**（pr-merged PR #23，https://github.com/99yyy/cantoai-analysis/pull/23 ，分支 `chore/r4-verify-pr21-6982`，标题 docs(round-4): record GitHub routine trigger for PR #21；merge `5755193`；CST 2026-09-18 ≈16:57）
