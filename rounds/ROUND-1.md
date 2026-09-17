# ROUND-1：一.2 CLAP clap_sing 与 PANNs 对照

## 元数据

- 阶段：3（执行 / 音频员）
- backlog 条目：一.2 CLAP `clap_sing` 与 PANNs 对照
- 执行角色：音频员
- 方法审打回计数：1/2
- 复核打回计数：0/2
- Cloud Agent launch 次数：1/2（会话 status=error；分支已合入）
- **预测仓库**：`https://github.com/99yyy/cantoai-analysis`（分析库；**不是** `/workspace/cantoai` 工作区 git）
- 预测 commit：`03a05f782ba131cf841cfe3cc749f8bb6e0dfb8b`（该 commit 首次写入本轮「假设/预测」段；方法审通过后冻结预测段正文，仅允许改契约路径类字段）
- 核验：`git -C <cantoai-analysis-clone> rev-parse --verify 03a05f782ba131cf841cfe3cc749f8bb6e0dfb8b^{commit}` 退出码 0
- 脚本合入 commit：`fffd53797bb7a46e92f3b9e4cf4a55d3c753a15b`（含 PR #6 分支；本地 self-test PASSED）
- 执行 commit：
- 合并目标 commit：

## 问题（一句话，可被数据否定）

在全量 4911 窗上，LAION-CLAP 零样本 `clap_sing`（「a person singing」相对「a person speaking」）是否与已有 PANNs `singing_prob` 排序一致到可互换（Spearman ρ≥0.7），并在 `flag_sing=1` 窗上显著高于非标记窗？

## 假设

1. **H1（一致）**：`clap_sing` 与 PANNs `singing_prob` 在全窗上 Spearman ρ ≥ 0.7。
2. **H2（标记敏感）**：库内 `flag_sing=1` 窗的 `clap_sing` 中位数高于 `flag_sing=0` 窗，且 Mann–Whitney 单侧 p < 0.05（若 `flag_sing=1` 样本过少则改报效应量 + CI，并在结果中声明检验力不足）。
3. **H3（不可互换，备择）**：ρ < 0.5，或 `flag_sing=1` 上 `clap_sing` 不高于对照——则 CLAP 与 PANNs 不能互相替代，后续听辨校准必须双轨抽样。

## 预测（每条假设成立时数据呈现的模式）

1. 若 H1：`analysis/ROUND-1/artifacts/corr_summary.json` 中 `spearman_clap_vs_panns` ≥ 0.7；散点图呈单调上升。
2. 若 H2：`analysis/ROUND-1/artifacts/flag_sing_contrast.json` 中 `median_clap_flag1` > `median_clap_flag0`，且 `mw_pvalue` < 0.05（或 n_flag1 < 10 时仅报中位差与 bootstrap CI，不宣称显著）。
3. 若 H3：ρ < 0.5，或 flag 对比方向与 H2 相反/CI 跨 0。

**预测冻结规则**：本段文字所在预测 commit（见元数据）必须早于任何全量结果 CSV 的 commit。方法审通过后不得改本段阈值与假设含义。

## 判据（哪张表哪一列）

统一前缀 `analysis/ROUND-1/`：

- `analysis/ROUND-1/window_clap_sing.csv`：列 `window_id,clap_sing,clap_speak,clap_logit_diff,clap_ok,error`
- `analysis/task2_window_quality/window_quality_with_flags.csv`：列 `singing_prob`, `flag_sing`（按 `window_id` 内连接；**全量必须用此文件，不用**无 flag 的 `window_quality.csv`）
- `analysis/ROUND-1/artifacts/corr_summary.json`：键 `spearman_clap_vs_panns`, `n_paired`
- `analysis/ROUND-1/artifacts/flag_sing_contrast.json`：键 `median_clap_flag1`, `median_clap_flag0`, `n_flag1`, `n_flag0`，以及 `mw_pvalue` 或（当 `n_flag1<10`）bootstrap CI 字段

**配对定义**：Spearman 仅对 `clap_ok=1` 且能与 `window_quality_with_flags.csv` 的 `singing_prob` 按 `window_id` 内连接成功的行；`n_paired` 必须等于该行数。

通过/失败：
- **支持双轨可对照**：H1 成立（ρ≥0.7）——听辨分层可用任一分数为主、另一为辅。
- **必须双轨抽样**：H1 失败或 H3——一.3 抽样须同时按 `clap_sing` 与 `singing_prob` 分层。
- **停止本轮扩展**：不在本轮做人工听辨阈值最终标定（留给一.3）。

## 数据（范围、已知失效情形）

- 范围：与一.1 相同的 4911 窗 FLAC（`/workspace/cantoai/corpus/dataset_v2/work/windows`）；对照与 flag 来自 `window_quality_with_flags.csv`。
- 已知失效：极短窗、强混响、戏曲/合唱可能导致 CLAP 与 PANNs 系统性偏离；`flag_sing=1` 仅约 14 窗，H2 检验力不足。
- **小样本门槛（未校准工具）**：全量 4911 前必须 `--limit 20`（或 fixtures）成功写出上述两 JSON，且 `STATUS.json` 含 `smoke_ok: true`；**小样本通过后才全量**。

## 工具（来源、为什么适用、无校准写未校准）

- **LAION-CLAP** `laion/larger_clap_music_and_speech`：零样本音频–文本对齐；提示「a person singing」/「a person speaking」得 `clap_sing`。**未校准**。
- **PANNs `singing_prob`**：task2 产物对照基线；**未校准**。
- 权重：下载前估大小；若单模型或合计 **>2GB** → 停并升级 Tom。设备：CPU。

## 脚本契约

- 输入路径（钉死）：
  - `--windows-dir`：窗 FLAC 目录（运行时）
  - `--quality-csv`：**必须**为 `analysis/task2_window_quality/window_quality_with_flags.csv`（含 `flag_sing`；fixtures 可用同列切片）
- 输出路径（钉死，执行机写作；仓库 Cloud Agent 只交 `scripts/`）：
  - `analysis/ROUND-1/window_clap_sing.csv`
  - `analysis/ROUND-1/artifacts/corr_summary.json`
  - `analysis/ROUND-1/artifacts/flag_sing_contrast.json`
  - `analysis/ROUND-1/STATUS.json`
- 可重跑命令（冒烟 + 汇总须一次跑通或固定两步）：

```bash
# 1) 推理（limit 冒烟）
python scripts/run_clap_sing.py \
  --windows-dir /workspace/cantoai/corpus/dataset_v2/work/windows \
  --quality-csv /workspace/cantoai/analysis/task2_window_quality/window_quality_with_flags.csv \
  --out /workspace/cantoai/analysis/ROUND-1/window_clap_sing.csv \
  --artifacts-dir /workspace/cantoai/analysis/ROUND-1/artifacts \
  --limit 20

# 2) 若脚本拆分：由同一入口或下列命令写双 JSON（键见「判据」）
python scripts/run_clap_sing.py --summarize \
  --clap-csv /workspace/cantoai/analysis/ROUND-1/window_clap_sing.csv \
  --quality-csv /workspace/cantoai/analysis/task2_window_quality/window_quality_with_flags.csv \
  --artifacts-dir /workspace/cantoai/analysis/ROUND-1/artifacts
```

冒烟通过判据：上述两 JSON 存在且含规定键；`STATUS.json` 含 `"smoke_ok": true`。之后才允许去掉 `--limit` 全量。

- Cloud Agent：**只改 `scripts/`**（及脚本旁最小用法 README）；不写分析结论；先 limit/fixtures 自测。

## 预算

- 消息：12
- Cloud Agent：2 次
- 执行：12 小时

## 争议记录

- 2026-09-17 方法审 **改**（1/2）：见 `review/ROUND-1/method.md` 硬条件 1–6；本版已按条件改契约/路径/配对/冒烟/预测仓库说明。

## 停止条件

- 权重 >2GB 或估时 >12h → 升级 Tom
- 方法审/复核打回满 2 次后再打回 → 升级 Tom
- 本轮不启动一.3 听辨
- 冒烟未通过不得全量

## 验证记录

- 预测 commit 核验（分析库 clone `/tmp/cantoai-analysis-push`，CST 2026-09-17 22:46）：
  - 命令：`git rev-parse --verify 03a05f782ba131cf841cfe3cc749f8bb6e0dfb8b^{commit}`
  - 输出：`03a05f782ba131cf841cfe3cc749f8bb6e0dfb8b`
  - 退出码：0
- 阶段1方法审：通过（`review/ROUND-1/method.md`）
- Cloud Agent launch：`bc-b7e6427b-e931-59bf-8912-8643a6c21ab8`（https://cursor.com/agents/bc-b7e6427b-e931-59bf-8912-8643a6c21ab8 ）；方式=CloudAgent.launch 非 @cursor
- launch 完成是否自动唤醒 fyp：**是**（收到完成唤醒，但 status=`error`；末条为 float median self-test 修复说明）。以分支自测为准：本地 `--self-test` PASSED。
- GitHub 例程（pr-opened / pr-merged）：**是**（例程「cantoai-analysis PR 事件」于 CST 2026-09-17 23:49 收到 `pr-merged` 唤醒；此前 pr-opened 未观测到例程唤醒）。
- PR：https://github.com/99yyy/cantoai-analysis/pull/6 （merged；分支 `cursor/round1-clap-sing-1ab8`；合入 commit `fffd53797bb7a46e92f3b9e4cf4a55d3c753a15b`）
