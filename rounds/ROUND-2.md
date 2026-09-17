# ROUND-2：一.3 人工听辨 200 窗抽样与 listening_sheet

## 元数据

- 阶段：1（方法审中）
- backlog 条目：一.3 人工听辨样本 200 窗抽样与 `listening_sheet`
- 执行角色：分析员（抽样表）+ 音频员（可选导出短音频切片路径清单）；**标注由 Tom**
- 方法审打回计数：0/2
- 复核打回计数：0/2
- Cloud Agent launch 次数：0/2
- **预测仓库**：`https://github.com/99yyy/cantoai-analysis`
- 预测 commit：（本文件首次合入 main 的 commit）
- 结果 commit：
- 执行 commit：
- 合并目标 commit：

## 问题（一句话，可被数据否定）

在按 `clap_sing`×`singing_prob` 双轨分层抽得的约 200 窗听辨集上，人工标签（dialogue / singing / recitation / mixed / transcription_error）是否足以标定两侧分数的可用阈值，使得「高 clap 且高 PANNs」窗的人工 singing 比例显著高于「双低」窗（风险差 ≥20pp 或等价检验 p&lt;0.05）？

## 假设

1. **H1（双高富集）**：处于 `clap_sing` 与 `singing_prob` 各自上四分位的窗，人工 `singing`（含 mixed 中以唱为主，若编码允许）比例比双下四分位高 ≥20pp。
2. **H2（单侧不可靠）**：仅按 PANNs 上四分位、或仅按 CLAP 上四分位抽得的「高分」窗，其人工 singing 比例相差 ≥15pp（呼应 ROUND-1 ρ≈0.40）。
3. **H3（film 混杂）**：`film_flag=1` 子集中，人工 `recitation`/`mixed` 占比高于 contemporary，说明电影窗不能只用 singing 阈值清洗。

## 预测（每条假设成立时数据呈现的模式）

1. 若 H1：`metrics/label_by_quadrant.json` 中 `singing_rate_both_high - singing_rate_both_low ≥ 0.20`。
2. 若 H2：`metrics/single_track_gap.json` 中 `|singing_rate_panns_high_only - singing_rate_clap_high_only| ≥ 0.15`。
3. 若 H3：`metrics/label_by_film.json` 中 film 的 `recitation_or_mixed_rate` 高于 contemporary 至少 10pp。

**预测冻结规则**：本段所在预测 commit 必须早于任何带人工标签的结果 commit。

## 判据（哪张表哪一列）

- `analysis/ROUND-2/listening_sheet.csv`：至少含 `window_id,video_id,film_flag,clap_sing,singing_prob,var_db,stratum,human_label,annotator_note`；`human_label ∈ {dialogue,singing,recitation,mixed,transcription_error,unset}`
- `analysis/ROUND-2/sample_manifest.json`：目标 n、各层配额、随机种子、实际抽中列表
- `analysis/ROUND-2/metrics/label_by_quadrant.json` 等（**仅在 Tom 标注完成后**由脚本汇总；本轮脚本阶段先交付抽样子与空标签列）

通过/失败（标注完成后）：
- H1 成立 → 双轨联合阈值可用于后续清洗。
- H1 失败或 H2 成立 → 维持双轨或改人工规则，不得只靠单分数。
- **审批点**：`listening_sheet.csv` 抽样就绪（标签列全为 `unset`）时 **必须通知 Tom** 开始听辨；未标注完成前不进入「标注后汇总」裁决。

## 数据（范围、已知失效情形）

- 范围：4911 窗；连接 `ROUND-1/window_clap_sing.csv`、`window_quality_with_flags.csv`、`task_calib_demucs_var/window_var_db.csv`、视频 `film_flag`。
- 抽样设计（钉死）：
  - 总目标 **200** 窗；其中 film≈160、contemporary≈40（可按实际 film 池调整，但须在 manifest 写明）。
  - **强制纳入** 全部 `flag_sing=1`（约 14）并计入 200 或单独附录列 `forced_flag_sing`。
  - 在 film / contemporary 内，对 `clap_sing` 与 `singing_prob` 做四分位交叉（或 3×3 粗栅格），各层按配额随机抽；种子写死在 manifest。
- 已知失效：人工标签主观；短窗难判；transcription_error 与内容类可并存时以 ROUND 编码规则为准（若冲突标 `mixed` 并 note）。

## 工具（来源、为什么适用、无校准写未校准）

- 分层抽样：pandas；分数来自 ROUND-1 / task2 / demucs（**CLAP/PANNs 仍未校准**——本轮目的即校准）。
- 不在本轮跑新大模型。

## 脚本契约

- 输入：
  - `analysis/ROUND-1/window_clap_sing.csv`
  - `analysis/task2_window_quality/window_quality_with_flags.csv`
  - `analysis/task_calib_demucs_var/window_var_db.csv`（可选列）
  - 视频 flag 表（`task3_multilabel_flags` 或等价）
- 输出：
  - `analysis/ROUND-2/listening_sheet.csv`（初始 `human_label=unset`）
  - `analysis/ROUND-2/sample_manifest.json`
  - `analysis/ROUND-2/STATUS.json`
- 命令示例：

```bash
python scripts/build_listening_sheet.py \
  --clap-csv analysis/ROUND-1/window_clap_sing.csv \
  --quality-csv analysis/task2_window_quality/window_quality_with_flags.csv \
  --flags-csv analysis/task3_multilabel_flags/video_multilabel_flags.csv \
  --out-dir analysis/ROUND-2 \
  --n-total 200 --n-film 160 --n-contemporary 40 --seed 20260918
```

- Cloud Agent：只改 `scripts/` + 最小 README；fixtures 上冒烟生成迷你 sheet。
- 标注后汇总可另命令 `--summarize-labels`（方法审可要求预留）。

## 预算

- 消息：12
- Cloud Agent：2 次
- 执行：12 小时（抽样应分钟级；听辨在 Tom 侧）

## 争议记录

-

## 停止条件

- 抽样表就绪 → **升级/通知 Tom**（审批点，非事故）
- 打回满额 → 升级 Tom
- 本轮不做全库清洗落库

## 验证记录

- launch 完成是否自动唤醒 fyp：
- GitHub 例程是否触发：
