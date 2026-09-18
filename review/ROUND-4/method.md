# ROUND-4 阶段1 · 方法审

- 输入：`rounds/ROUND-4.md` + `rounds/ROUND-4.yaml`（打回计数将记 1/2）
- 判定：**改**
- 核验基线：`origin/main` @ `40d92a1`（含 PR #14）；`checks.json` 与 `data/corpus_v2.sqlite`

## 四项检查

| # | 项 | 结果 |
|---|----|------|
| 1 | 工具适用 | **满足**。本轮是契约/CI 修补，工具为 `tests` / `contract-check` / `scope-check`；不跑音频推断，与问题匹配。`singing_prob_source` 仅钉住 ROUND-3 遗留，不新增推断。 |
| 2 | 判据可重算 | **满足**。合并闸门=三检查全绿；四条新规则可由 `contract_check` 静态重算；语料 sha256 `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f` 与 `sha256sum data/corpus_v2.sqlite` 及 `frame.yaml: inputs.corpus_sha256` 一致。 |
| 3 | 预测写死 | **不满足**。见硬条件 1。 |
| 4 | write_scopes 两两不相交 | **满足**。`impl`∈{src,sql,frame.yaml}、`tests`∈{tests/}、`review`∈{review/ROUND-4/}；用 `fnmatch` 对候选路径无多归属。 |

## 硬条件（必须全部满足才算方法审通过）

### 1. 修正预测第 2 条（当前状态描述错误）

`rounds/ROUND-4.md` §预测 第 2 条现写：当前 main 上「已知红」的四条（`assertion_message_set`、`select_from_only_load_sql`、`no_measure_fillna_or_get_default`、`mutations_killed`）在 impl 合入后「转绿」。

**事实**：`origin/main` 的 `checks.json` 中上述四条均为 `PASS`（36/36 PASS）。`src/merge.py` 仍含 `enforce_expected` 与无门的 `left_attach`，问题本身成立，但「已知红→转绿」基线不实，预测不能冻结。

**可验证通过条件**（须经 PR 改 `rounds/ROUND-4.md` 后复审）：

1. `rg -n '已知红' rounds/ROUND-4.md` 退出码 **1**（无匹配）。
2. §预测 第 2 条改为（或语义等价）：上述四条在 **impl 合入（且已 rebase 含 tests）后仍为 `PASS`**（不得因删除 `enforce_expected` / 改 `left_attach` 而转红）；**禁止**再写它们在当前 main 上为红或「转绿」。
3. `python3 -c "import json; c=json.load(open('checks.json')); n=['assertion_message_set','select_from_only_load_sql','no_measure_fillna_or_get_default','mutations_killed']; assert all(x['status']=='PASS' for x in c if x['name'] in n)"` 在预测冻结 commit 上退出码 **0**（证明基线为绿，与改写后的预测一致）。

## Advisory（不计打回）

- 预测第 1 条规则名「以 impl 落地为准」可接受，因要求 tests 反例能杀死缺失实现。
- 本轮 `comparisons: []`、无 comparison 波，与 LOOP「ROUND-3 的后记」一致。
- 音频员不跑推断：规格已写明，无异议。

## 结论

**改。** 仅硬条件 1。满足并合入后请再派阶段1复审（计数 1/2）。在此之前不要 launch wave1 impl/tests。
