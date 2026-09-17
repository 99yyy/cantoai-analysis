# ROUND-1：一.2 CLAP clap_sing 与 PANNs 对照

## 元数据

- 阶段：1（方法审中）
- backlog 条目：一.2 CLAP `clap_sing` 与 PANNs 对照
- 执行角色：音频员
- 方法审打回计数：0/2
- 复核打回计数：0/2
- Cloud Agent launch 次数：0/2
- 预测 commit：`03a05f782ba131cf841cfe3cc749f8bb6e0dfb8b`（本文件首次合入；方法审通过后冻结预测段）
- 结果 commit：
- 执行 commit：
- 合并目标 commit：

## 问题（一句话，可被数据否定）

在全量 4911 窗上，LAION-CLAP 零样本 `clap_sing`（「a person singing」相对「a person speaking」）是否与已有 PANNs `singing_prob` 排序一致到可互换（Spearman ρ≥0.7），并在 `flag_sing=1` 窗上显著高于非标记窗？

## 假设

1. **H1（一致）**：`clap_sing` 与 PANNs `singing_prob` 在全窗上 Spearman ρ ≥ 0.7。
2. **H2（标记敏感）**：库内 `flag_sing=1` 窗的 `clap_sing` 中位数高于 `flag_sing=0` 窗，且 Mann–Whitney 单侧 p < 0.05（若 `flag_sing=1` 样本过少则改报效应量 + CI，并在结果中声明检验力不足）。
3. **H3（不可互换，备择）**：ρ < 0.5，或 `flag_sing=1` 上 `clap_sing` 不高于对照——则 CLAP 与 PANNs 不能互相替代，后续听辨校准必须双轨抽样。

## 预测（每条假设成立时数据呈现的模式）

1. 若 H1：`artifacts/corr_summary.json` 中 `spearman_clap_vs_panns` ≥ 0.7；散点图呈单调上升。
2. 若 H2：`artifacts/flag_sing_contrast.json` 中 `median_clap_flag1` > `median_clap_flag0`，且 `mw_pvalue` < 0.05（或 n_flag1 < 10 时仅报中位差与 bootstrap CI，不宣称显著）。
3. 若 H3：ρ < 0.5，或 flag 对比方向与 H2 相反/CI 跨 0。

**预测冻结规则**：本段文字所在 commit 必须早于任何全量结果 CSV 的 commit。

## 判据（哪张表哪一列）

- `analysis/ROUND-1/window_clap_sing.csv`：`window_id`, `clap_sing`, `clap_speak`, `clap_logit_diff`（或等价：sing 与 speak 的相似度之差/温度归一概率）
- `task2_window_quality/window_quality.csv`：`singing_prob`（按 `window_id` 内连接）
- `fixtures/sample.sqlite` / 全库 windows：`flag_sing`
- `analysis/ROUND-1/artifacts/corr_summary.json`：`spearman_clap_vs_panns`, `n_paired`
- `analysis/ROUND-1/artifacts/flag_sing_contrast.json`：中位数、n、检验统计

通过/失败：
- **支持双轨可对照**：H1 成立（ρ≥0.7）——听辨分层可用任一分数为主、另一为辅。
- **必须双轨抽样**：H1 失败或 H3——一.3 抽样须同时按 `clap_sing` 与 `singing_prob` 分层。
- **停止本轮扩展**：不在本轮做人工听辨阈值最终标定（留给一.3）。

## 数据（范围、已知失效情形）

- 范围：与一.1 相同的 4911 窗 FLAC（`corpus/dataset_v2/work/windows`）；对照列来自已有 `window_quality.csv`。
- 已知失效：极短窗、强混响、戏曲/合唱可能导致 CLAP 与 PANNs 系统性偏离；`flag_sing=1` 极少，H2 可能检验力不足。
- fixtures：脚本必须在无真实音频时用合成/跳过策略仍能 `--help` 与契约自检；有 fixtures 音频或 sample 窗列表时先冒烟。

## 工具（来源、为什么适用、无校准写未校准）

- **LAION-CLAP** `laion/larger_clap_music_and_speech`：零样本音频–文本对齐；提示「a person singing」/「a person speaking」得 `clap_sing`。**未校准**（无本语料听辨阈值；本轮只做与 PANNs 相关与 flag 对比）。
- **PANNs `singing_prob`**：已有 task2 产物，作对照基线；其歌唱类定义与粤语戏曲/口白边界**未校准**。
- 权重：下载前估大小；若单模型或合计 **>2GB** → 停并升级 Tom。设备：CPU。

## 脚本契约

- 输入路径：
  - 窗音频目录（运行时参数）
  - `task2_window_quality/window_quality.csv`（或 fixtures 切片）
  - 可选：`flag_sing` 来源（sqlite 或 CSV）
- 输出（仓库 `scripts/` 只写脚本；全量产物在执行机 `analysis/ROUND-1/`）：
  - `window_clap_sing.csv` 列：`window_id,clap_sing,clap_speak,clap_logit_diff,clap_ok,error`
  - `artifacts/corr_summary.json`, `artifacts/flag_sing_contrast.json`
  - `STATUS.json`（长任务）
- 一条命令可重跑（示例，以 PR 内 README 为准）：

```bash
python scripts/run_clap_sing.py --windows-dir PATH --quality-csv PATH --out window_clap_sing.csv --limit 20
```

- Cloud Agent：**只改 `scripts/`**（及本轮 `task` 目录下脚本 README 用法）；不写分析结论；先 fixtures/limit 自测。

## 预算

- 消息：12
- Cloud Agent：2 次
- 执行：12 小时

## 争议记录

-

## 停止条件

- 权重 >2GB 或估时 >12h → 升级 Tom
- 方法审/复核打回满 2 次后再打回 → 升级 Tom
- 本轮不启动一.3 听辨

## 验证记录（可选）

- launch 完成是否自动唤醒 fyp：
- GitHub 例程（pr-opened / pr-merged）是否触发：
