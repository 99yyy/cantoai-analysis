# ROUND-2：一.3 人工听辨 200 窗抽样与 listening_sheet

## 元数据

- 阶段：3（抽样完成；Tom 部分标注进行中——标多少用多少）
- backlog 条目：一.3 人工听辨样本 200 窗抽样与 `listening_sheet`
- 执行角色：分析员（抽样表）+ 音频员（可选导出短音频切片路径清单）；**标注由 Tom**
- 方法审打回计数：1/2
- 复核打回计数：0/2
- Cloud Agent launch 次数：1/2（完成；PR #7 已合入）
- **预测仓库**：`https://github.com/99yyy/cantoai-analysis`
- 预测 commit：`fffad05152daaf603bef1d99f9e931831b04e0a6`（假设/预测数值门槛冻结于该 commit；本修订只改契约路径、可重算定义与抽样规则）
- 脚本合入 commit：
- 工作区执行 commit：`decfb76`
- 结果 commit：`6b76d2cb1ab42957671647095a91c0017f79792a`（分析库；工作区 `decfb76`）
- 执行 commit：
- 合并目标 commit：
- **Cloud Agent**：PR #7 已合入；抽样表已交付

## 问题（一句话，可被数据否定）

在按 `clap_sing`×`singing_prob` 双轨分层抽得的约 200 窗听辨集上，人工标签是否足以标定两侧分数，使得「双高」窗的 `singing_rate` 比「双低」窗高 ≥20pp？

## 假设

1. **H1（双高富集）**：`both_high` 层的 `singing_rate` 比 `both_low` 高 ≥20pp。
2. **H2（单侧不可靠）**：`|singing_rate_panns_high_only - singing_rate_clap_high_only| ≥ 0.15`。
3. **H3（film 混杂）**：film 子集的 `recitation_or_mixed_rate` 比 contemporary 高 ≥10pp。

## 预测（每条假设成立时数据呈现的模式）

1. 若 H1：`analysis/ROUND-2/metrics/label_by_quadrant.json` 中 `singing_rate_both_high - singing_rate_both_low ≥ 0.20`。
2. 若 H2：`analysis/ROUND-2/metrics/single_track_gap.json` 中 `|singing_rate_panns_high_only - singing_rate_clap_high_only| ≥ 0.15`。
3. 若 H3：`analysis/ROUND-2/metrics/label_by_film.json` 中 film 的 `recitation_or_mixed_rate - contemporary_recitation_or_mixed_rate ≥ 0.10`。

**预测冻结规则**：预测数值门槛所在 commit（见元数据）必须早于任何带人工标签的结果 commit。方法审通过后不得改上述三个不等式。

## 判据（哪张表哪一列）

### 标签与比率（可机器重算）

- `human_label ∈ {dialogue,singing,recitation,mixed,transcription_error,unset}`
- 分母：该层 `human_label != "unset"` 的行
- **`singing_rate` := `mean(human_label == "singing")`**（**不含** `mixed`；已删除「以唱为主」无编码条件）
- **`recitation_or_mixed_rate` := `mean(human_label in {"recitation","mixed"})`**

### 四分位切点与层（抽样前、全库）

在 **抽样前**，对全量可配对窗（`clap_ok=1` ∩ quality ∩ window flags ∩ var）计算四分位：

- `q1_clap,q3_clap`：`clap_sing` 的 25%/75% 分位
- `q1_panns,q3_panns`：`singing_prob` 的 25%/75% 分位
- 全部写入 `sample_manifest.json`

层定义（**选定四分位交叉，不用 3×3**）：

| `stratum` | 定义 |
|-----------|------|
| `both_high` | `clap_sing≥q3_clap ∧ singing_prob≥q3_panns` |
| `both_low` | `clap_sing≤q1_clap ∧ singing_prob≤q1_panns` |
| `panns_high_only` | `singing_prob≥q3_panns ∧ clap_sing<q3_clap` |
| `clap_high_only` | `clap_sing≥q3_clap ∧ singing_prob<q3_panns` |
| `mid` | 其余可配对窗 |

抽样在 `film_flag=1` / `film_flag=0`（contemporary）内按上述 `stratum` 配额随机抽；`stratum` 列写入 sheet。


### 部分标注与阶段4汇总（Tom 2026-09-18 定）

听辨工具按 `stratum` **轮流出题**，任意时刻停下时，已标行在五层上严格均衡（例：标 25→每层 5；标 100→每层 20）；film/contemporary 约 80/20。因此**部分标注是合法分层随机子样本**，不是残缺数据。

阶段4 / `--summarize-labels`（及审稿复核）必须：

1. **只统计** `human_label != "unset"` 的行；其余保持 `unset`，不删除、不填补、不把 unset 当缺失插补进比率分母之外的用途。
2. **先按层算**各层比率，再用每层原定配额权重 **40**（`n_stratum_design=40`）回推整体/对照量；**禁止**对已标行做简单未加权平均当成总体估计。
3. 每个关键数字附 **按视频重采样** 的 bootstrap **95% CI**，并列出 **每层实际已标 n**。
4. 报告必须写清：以当前已标 n，区间是否窄到能回答本轮问题（尤其「老电影/低分里唱段到底占多少」）；若不够，**直接给出还需要大约多少条**，**不要硬下结论**，也**不要暂停等待** Tom 继续标。
5. `annotator_note` 中含标记 **`saw_meta`** 的行：单独统计数量与占比；若占比偏高，在报告里提醒可能存在锚定效应（标标注时看过机器分数）。

### 产物路径

- `analysis/ROUND-2/listening_sheet.csv`：列 `window_id,video_id,film_flag,clap_sing,singing_prob,var_db,stratum,human_label,annotator_note,forced_flag_sing`；初始 `human_label=unset`
- `analysis/ROUND-2/sample_manifest.json`：至少含 `seed,n_total,n_film,n_contemporary,q1_clap,q3_clap,q1_panns,q3_panns,stratum_quotas,window_ids,forced_flag_sing_ids,forced_in_quota`
- `analysis/ROUND-2/STATUS.json`：至少含 `smoke_ok`（bool）
- 标注后：`metrics/label_by_quadrant.json`、`metrics/single_track_gap.json`、`metrics/label_by_film.json`（键与预测段一致）

通过/失败（**部分标注即可裁决，不必等满 200**）：
- H1 成立 → 双轨联合阈值可用。
- H1 失败或 H2 成立 → 维持双轨，不得只靠单分数。
- **审批点（已完成）**：sheet 就绪时已通知 Tom。
- **交付变更（Tom 2026-09-18 定）**：Tom 标多少算多少；收到任意一批已标行即可跑阶段4汇总，**不要等满 200，也不要暂停等 Tom**。

## 数据（范围、已知失效情形）

- 范围：4911 窗；连接 ROUND-1 clap CSV、quality with flags、`window_var_db.csv`、**窗级** `window_multilabel_flags.csv`。
- 抽样设计（钉死）：
  - `n_total=200`；`n_film=160`；`n_contemporary=40`（池不够则在 manifest 记录实际数并按比例缩）。
  - **`flag_sing=1` 规则 A**：全部强制纳入，**计入** `n_total=200`（`forced_in_quota: true`）；`forced_flag_sing_ids` 列出这些 id。
  - 栅格：**四分位交叉**（上表五层）；`seed=20260918`。
- 已知失效：人工主观；短窗难判；`transcription_error` 与内容类冲突时标 `mixed` 并 note。

## 工具

- pandas 分层抽样；分数未校准（本轮用于标定）。不跑新大模型。

## 脚本契约

- 输入（钉死）：
  - `--clap-csv analysis/ROUND-1/window_clap_sing.csv`
  - `--quality-csv analysis/task2_window_quality/window_quality_with_flags.csv`
  - `--var-csv analysis/task_calib_demucs_var/window_var_db.csv`
  - `--flags-csv analysis/task3_multilabel_flags/window_multilabel_flags.csv`（窗级 `film_flag`；**不用**视频表）
- 输出：`listening_sheet.csv`、`sample_manifest.json`、`STATUS.json`（路径见上）
- 命令：

```bash
# 冒烟（fixtures 或 --limit）
python scripts/build_listening_sheet.py \
  --clap-csv PATH --quality-csv PATH --var-csv PATH --flags-csv PATH \
  --out-dir analysis/ROUND-2 \
  --n-total 200 --n-film 160 --n-contemporary 40 --seed 20260918 \
  --limit 50

# 全量抽样（仅 smoke_ok 后）
python scripts/build_listening_sheet.py \
  --clap-csv analysis/ROUND-1/window_clap_sing.csv \
  --quality-csv analysis/task2_window_quality/window_quality_with_flags.csv \
  --var-csv analysis/task_calib_demucs_var/window_var_db.csv \
  --flags-csv analysis/task3_multilabel_flags/window_multilabel_flags.csv \
  --out-dir analysis/ROUND-2 \
  --n-total 200 --n-film 160 --n-contemporary 40 --seed 20260918

# 标注后汇总（预留）
python scripts/build_listening_sheet.py --summarize-labels \
  --sheet analysis/ROUND-2/listening_sheet.csv \
  --manifest analysis/ROUND-2/sample_manifest.json \
  --out-dir analysis/ROUND-2/metrics
```

- **冒烟门槛**：全量抽样前，fixtures 或 `--limit` 必须成功；`STATUS.json` 含 `"smoke_ok": true`；迷你 `listening_sheet.csv` 行数≥1 且 `human_label` 全为 `unset`。
- Cloud Agent：只改 `scripts/` + 最小 README；**04:20 HKT 前不 launch**。

## 预算

- 消息：12
- Cloud Agent：2 次
- 执行：12 小时（抽样分钟级；听辨在 Tom 侧）

## 争议记录

- 2026-09-18 **部分标注交付变更**（Tom 定）：标多少用多少；五层轮流出题→已标子集合法；阶段4按层加权(设计n=40)+视频bootstrap CI+saw_meta 计数；不够则报所需增量，不等满200。
- 2026-09-18 阶段1 **改**（1/2）：`review/ROUND-2/method.md` 硬条件 1–6；本版已钉死窗级 film_flag、全库四分位层、singing_rate 枚举、flag_sing 规则 A、CLI/冒烟。

## 停止条件

- 冒烟未通过 → 不得全量抽样
- 抽样表就绪 → **通知 Tom**（审批点，已做）
- 部分标注即可汇总；**不等满 200**
- 打回满额 → 升级 Tom
- 本轮不做全库清洗落库

## 验证记录

- Cloud Agent launch：`bc-34f41e9c-fae5-541c-96a3-135550c48b29`（https://cursor.com/agents/bc-34f41e9c-fae5-541c-96a3-135550c48b29 ）
- launch 完成是否自动唤醒 fyp：**是**（status=finished，PR #7）
- GitHub 例程（待事件）：
- GitHub 例程是否触发：

- 阶段1复审：通过（`review/ROUND-2/method.md`，CST 2026-09-18 ≈00:23）；预测门槛仍冻结于 `fffad051…`；Cloud Agent 不早于约 04:20 HKT launch。
