# ROUND-3 阶段1 · 方法审（复审）

- 输入：`rounds/ROUND-3.md` + `rounds/ROUND-3.yaml`（打回后修订；计数将记 2/2）
- 判定：**改**
- 对照：首版硬条件 1–5

## 硬条件逐条复核

| # | 条件 | 复核 | 结果 |
|---|------|------|------|
| 1 | 契约文件可核验 | `.cursor/rules/analysis-contract.mdc` 存在；`sha256sum` = `461e8928597b1269be05088f3296663b896f1a5c4d264c2d7be3cf41ad5db3e5`；元数据 commit 更正为 `228c78a`（clone 内可 `rev-parse`） | **满足** |
| 2 | H2/H3 `singing_prob` 钉死 PANNs 整窗 | md/yaml 写明仅 `task2_window_quality/window_quality_with_flags.csv`；`singing_prob_source` 块；禁止与 CLAP 同表 | **满足** |
| 3 | H3 阈值统一 | md 预测与 yaml 均为 `abs(delta_pp) ≤ 0.5` | **满足** |
| 4 | 脚本契约钉死输入 + 禁推理 | 列出 corpus / window_quality / clap（本轮不读）/ frame / ROUND-3.yaml；禁止 `run_clap*` 等推理入口 | **满足** |
| 5 | 预测 commit 可 `rev-parse` | 元数据写 `d6f1132a1fdfddffb36d6855e322580b22e9dc9c`，但在 `/tmp/cantoai-analysis-push`（及可及远端 fetch）上 **`git rev-parse --verify d6f1132a1fdfddffb36d6855e322580b22e9dc9c^{commit}` 失败**（bad object）。工作区 ROUND 已含冻结文，但该 hash **不是**分析库中的真实 commit | **不满足** |

## 仍须满足的硬条件（仅第 5 条）

### 5. 预测 commit 必须是真实 git 对象

**通过条件**（在分析库 clone 上）：

```bash
git -C <cantoai-analysis-clone> rev-parse --verify d6f1132a1fdfddffb36d6855e322580b22e9dc9c^{commit}
# 或若改用新 hash：先把含冻结预测三不等式的 ROUND-3.md/.yaml 提交并 push，
# 再把元数据「预测 commit」改为该真实 hash，且下行退出码 0：
git -C <cantoai-analysis-clone> rev-parse --verify <新预测commit>^{commit}
```

且该 commit 的树中 `rounds/ROUND-3.md` 预测段已含 H1/H2/H3 冻结不等式（含 `abs(delta_pp) ≤ 0.5` 与 PANNs 来源）。

> 说明：方法审「通过」不得早于预测 commit 落库；仅在文件里写一个尚不存在的 hash 不算冻结。

## advisory

- 条件 1–4 已齐，复审只卡预测 commit 落库。
- 本机无法 `git fetch` GitHub（无凭证）；以 clone 内对象为准。若 hash 仅在未推送的本地，请 push 后派复审。
- 通过前仍 **不** launch 阶段2。

## 结论

**改**（计数 **2/2**）。仅硬条件 5 未过：把真实预测 commit 写入元数据并确保 `rev-parse` 退出码 0 后再派阶段1终审。满额后再改则按 LOOP 升级 Tom。
