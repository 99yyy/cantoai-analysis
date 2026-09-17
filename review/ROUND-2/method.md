# ROUND-2 阶段1 · 方法审

- 输入：`rounds/ROUND-2.md`（方法审打回计数 1/2）
- 判定：**改**
- 范围：只审跑之前的方法/契约；不预审标注质量

## 已核对（可保留）

- 问题可证伪；H1/H2/H3 有数值门槛；预测段已写死，预测 commit `fffad05152daaf603bef1d99f9e931831b04e0a6` 在 `/tmp/cantoai-analysis-push` 可 `rev-parse`。
- 分层抽样不依赖「已校准」CLAP/PANNs；本轮正是用人工标定未校准分数 → 工具适用性 **通过**（advisory：分位层是探索轴）。
- 本机输入存在：`analysis/ROUND-1/window_clap_sing.csv`（4911，列含 `clap_sing`）、`analysis/task2_window_quality/window_quality_with_flags.csv`（`singing_prob`,`flag_sing`；`flag_sing=1` 共 14）、`analysis/task3_multilabel_flags/window_multilabel_flags.csv`（`film_flag` 1:1077 / 0:3834，配额 160/40 可行）、`analysis/task_calib_demucs_var/window_var_db.csv`（`var_db`）。
- 审批点（sheet 就绪 → 通知 Tom）写清；未标注前不裁决 H1–H3 → 合理。

## 硬条件（必须全部满足才复审通过）

### 1. 钉死 `film_flag` 来源

当前契约示例只给 `analysis/task3_multilabel_flags/video_multilabel_flags.csv`，但 `listening_sheet.csv` 需要窗级 `film_flag`。

**通过条件**：`rounds/ROUND-2.md` 脚本契约输入改为（或并列并写明 join）：

`analysis/task3_multilabel_flags/window_multilabel_flags.csv`

命令行含对应参数。若坚持视频表，必须写明 `window_id`→`video_id` 规则 + join 键，并保证与 `window_multilabel_flags.csv` 的 `film_flag` 逐窗一致（例如 `--check`：两来源不符行数为 0）。

### 2. 四分位切点定义写死（全库，非样本内）

**通过条件**：判据段增加（或等价表）：

- 切点在 **抽样前**、对全量可配对窗（`clap_ok=1` ∩ quality ∩ flags）计算；
- `q1_clap,q3_clap,q1_panns,q3_panns` 写入 `sample_manifest.json`；
- `both_high` := `clap_sing≥q3_clap ∧ singing_prob≥q3_panns`；`both_low` := `clap_sing≤q1_clap ∧ singing_prob≤q1_panns`；
- `panns_high_only` := `singing_prob≥q3_panns ∧ clap_sing<q3_clap`；`clap_high_only` := `clap_sing≥q3_clap ∧ singing_prob<q3_panns`。

栅格方案须 **选定一种**（四分位交叉 **或** 3×3，不可写「或」留空），并钉死 `stratum` 层名。

### 3. `singing_rate` 分子可机器重算

H1「mixed 中以唱为主，若编码允许」与枚举 `{dialogue,singing,recitation,mixed,...}` 冲突，无法重算。

**通过条件**：判据写死其一：

- `singing_rate = mean(human_label == "singing")`（分母=该层 `human_label != "unset"`），**或**
- `singing_rate = mean(human_label in {"singing","mixed"})`，

并删除「以唱为主」无编码条件。H3：`recitation_or_mixed_rate = mean(human_label in {"recitation","mixed"})` 同样写死。

### 4. `flag_sing=1` 强制纳入规则二选一

**通过条件**：抽样设计只保留 **一条**：

- A：强制窗计入 `n_total=200`（manifest：`forced_in_quota: true`），或
- B：强制窗进附录/旁路且 **不减** 200 配额（`forced_in_quota: false`，另输出 `forced_flag_sing_ids`）。

禁止「计入 200 或单独附录」并存。

### 5. CLI 与产物键齐全（可冒烟）

**通过条件**：契约命令能一次（或固定两步）产出：

- `listening_sheet.csv`（列含判据所列；初始 `human_label=unset`）
- `sample_manifest.json`（至少：`seed`,`n_total`,`n_film`,`n_contemporary`,`q1_clap`,`q3_clap`,`q1_panns`,`q3_panns`,`stratum_quotas`,`window_ids`,`forced_flag_sing_ids`,`forced_in_quota`）
- `STATUS.json`（至少：`smoke_ok` bool）

并补上 `--var-csv analysis/task_calib_demucs_var/window_var_db.csv`（`var_db` 为 sheet 必列）。`--summarize-labels` 预留，且三个 metrics JSON 键与预测段一致。

### 6. 冒烟门槛

**通过条件**：全量抽样前，fixtures（或 `--limit` 小表）跑通，`STATUS.json` 含 `"smoke_ok": true`，迷你 `listening_sheet.csv` 行数≥1 且 `human_label` 全为 `unset`。ROUND 契约/停止条件写明此门槛。

## advisory（不计入打回）

- n=200、film 配额重，H2/H3 检验力有限；保留效应量即可。
- 人工标签主观；`transcription_error` 冲突规则已有一句，足够。
- 预测仓库 URL 以 ROUND 元数据 + 可 `rev-parse` 的 hash 为准（本审已核验 hash）。

## 结论

**改。** 满足硬条件 1–6 后改 `rounds/ROUND-2.md` 并再派阶段1复审；计数 1/2。
