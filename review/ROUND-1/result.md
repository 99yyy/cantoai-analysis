# ROUND-1 阶段4 · 结果复核

- 输入：`analysis/ROUND-1/`；`rounds/ROUND-1.md`（阶段4）
- 工作区结果 commit：`ccd89ba`；分析库结果 commit：`4eab466`；预测 commit：`03a05f782ba131cf841cfe3cc749f8bb6e0dfb8b`
- 判定：**通过**
- 复核打回计数：0/2（本轮无打回）

## 预测 commit 时序

| 检查 | 结果 |
|------|------|
| `/tmp/cantoai-analysis-push` 上 `03a05f7` 是 `4eab466` 的祖先 | **是**（`merge-base --is-ancestor` 退出码 0） |
| 预测时间 vs 首个全量 CSV commit | 预测 `2026-09-17 22:43 +0800`；工作区首次写入 `window_clap_sing.csv` 为 `ccd89ba`（`2026-09-18 00:14 +0800`） |
| 预测阈值/假设是否事后改写 | 冻结后仅路径前缀与冻结规则措辞有改（方法审允许的契约路径类）；ρ≥0.7 / H2 / H3 阈值未改 |

**结论**：预测早于结果，未见事后改预测阈值。

## 自写重算（禁止跑分析员脚本）

命令（venv 仅提供 pandas/scipy，不 import `run_clap_sing`）：

```bash
/workspace/cantoai/analysis/task_round1_clap_sing/.venv/bin/python \
  -c '...'  # 见 review/ROUND-1/recalc_key.json 生成逻辑
```

配对：`clap_ok==1` ∩ 与 `window_quality_with_flags.csv` 按 `window_id` 内连接，且 `clap_sing`/`singing_prob` 非空。

| 键 | 报告值 | 重算值 | 一致 |
|----|--------|--------|------|
| `n_paired` | 4911 | 4911 | 是 |
| `spearman_clap_vs_panns` | 0.400360455099 | 0.400360455099456 | 是（差 ~1e-13） |
| `median_clap_flag1` | -0.8015022 | -0.8015022 | 是 |
| `median_clap_flag0` | -1.5535928 | -1.5535928 | 是 |
| `n_flag1` / `n_flag0` | 14 / 4897 | 14 / 4897 | 是 |
| `mw_pvalue`（单侧 greater） | 0.0387107924852 | 0.038710792485197 | 是 |

重算产物：`review/ROUND-1/recalc_key.json`。

## 对照预测

| 假设 | 预测 | 观测（重算） | 判定 |
|------|------|--------------|------|
| H1 | ρ≥0.7 | ρ≈0.400 | **不成立** |
| H2 | med1>med0 且 MW p&lt;0.05 | -0.802 &gt; -1.554；p≈0.0387；n_flag1=14≥10 | **成立**（样本仍极小） |
| H3 | ρ&lt;0.5 或 flag 反方向 | ρ&lt;0.5；flag 方向不反 | **部分成立**（ρ 低） |

README / STATUS 实务结论「不能互换 → 一.3 须双轨分层」与判据一致。

## 无脚本支撑 / 缺口

- **散点图**：预测写「散点图呈单调上升」，`analysis/ROUND-1/` 下无 png/散点产物。判据未钉死图路径 → **advisory**（不阻塞）；建议一.3 前补一张 `clap_sing` vs `singing_prob` 散点便于沟通。
- **权重大小 779815910 B / 0.726 GiB**：仅见 `STATUS.json`，本复核未向 Hub 重取 → **advisory**（未触 2GB 帽的叙事可接受，但不可独立核验字节数）。
- 其余 README 关键数字均可追溯到 CSV/JSON。

## 替代解释（≥2；结论可能被推翻的方向）

1. **度量不可比导致「假低相关」**：`clap_sing` 是 singing/speaking 相对 logit，PANNs 是多标签概率；ρ≈0.4 可能主要来自尺度/任务定义差异，而非某一轨对粤语歌唱「更错」。若换成同空间的校准分数，H1 门槛叙述可能改变（但「不可直接互换原始分」的实务建议仍稳）。
2. **flag_sing=1 仅 14 窗，H2 不稳定**：MW p≈0.039 贴着 0.05；去掉 1–2 个戏曲/合唱极端窗或改用 bootstrap CI，可能失去「显著」。H2 支持应视为弱证据，不能单独支撑「CLAP 已对齐人工歌唱标记」。
3. **域与截断**：英文提示 + 最多 10s 截断 + music_and_speech 预训练域，可能系统压低 CLAP 与整窗 PANNs 的排序一致性；换提示或全长窗可能抬高 ρ，但当前数据下双轨抽样仍是稳健策略。

## 结论

**通过。** 关键数字可自写重算复现；预测 commit 早于结果；H1 失败 / H2 弱支持 / 须双轨 与数据一致。advisory：补散点图、权重大小勿当硬证据。可通知协调者向用户汇报本轮结论。
