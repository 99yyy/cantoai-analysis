# ROUND-1：CLAP `clap_sing` vs PANNs `singing_prob`

## 结论（对照假设）

| 假设 | 预测 | 观测 | 判定 |
|------|------|------|------|
| **H1** ρ≥0.7 | 可互换 | Spearman **ρ=0.400**（n_paired=4911） | **不支持** |
| **H2** flag_sing=1 中位更高且 MW 单侧 p&lt;0.05 | 标记敏感 | med_flag1=**-0.802** &gt; med_flag0=**-1.554**；**mw_pvalue=0.0387**（n_flag1=14） | **支持** |
| **H3** ρ&lt;0.5 或 flag 方向反 | 不可互换备择 | ρ=0.400&lt;0.5，且 flag 方向与 H2 一致 | **部分支持**（ρ 低；flag 不反） |

**实务含义**：CLAP 与 PANNs **不能互相替代**（H1 失败）。后续一.3 听辨抽样须 **双轨分层**（同时按 `clap_sing` 与 `singing_prob`）。`flag_sing=1` 上 CLAP 中位仍显著偏高（H2），但 n_flag1=14 检验力有限。

## 关键数字

| 项 | 值 |
|----|-----|
| 模型 | `laion/larger_clap_music_and_speech` |
| 权重大小（Hub 估） | 779,815,910 B ≈ **0.726 GiB**（&lt;2GB 帽） |
| 窗数 / clap_ok / 失败 | **4911 / 4911 / 0** |
| Spearman ρ / n_paired | **0.400** / **4911** |
| median_clap_flag1 / flag0 | **-0.8015** / **-1.5536** |
| n_flag1 / n_flag0 | **14** / **4897** |
| mw_pvalue（单侧 greater） | **0.0387** |
| 冒烟 | limit=20，推理 18.3s，wall≈49s，`smoke_ok=true` |
| 估时全量（冒烟外推） | **est_hours_full≈1.25 h** |
| 全量实测 | inference **1309.3 s**（≈0.36 h），wall 1314 s |

## 产物路径

- CSV：`/workspace/cantoai/analysis/ROUND-1/window_clap_sing.csv`
- `metrics/corr_summary.json`：`spearman_clap_vs_panns`, `n_paired`
- `metrics/flag_sing_contrast.json`：中位、n、`mw_pvalue`
- `STATUS.json`：含 `smoke_ok`、权重大小、est/实测时
- quality 对照：`/workspace/cantoai/analysis/task2_window_quality/window_quality_with_flags.csv`

## 反对解释（≥2）

1. **尺度与提示不匹配**：CLAP 输出为相对「singing vs speaking」的 logit，PANNs `singing_prob` 为多标签概率；ρ≈0.4 可能反映度量空间不同，而非「谁更懂歌唱」。单调相关弱不直接证明某一轨错误。
2. **flag_sing 极稀 + 选择偏倚**：仅 14 个 flag=1；MW p=0.0387 刚好过 0.05，对异常窗/戏曲/合唱敏感。H2「显著」可能不稳定；Bootstrap 或更大人工标集会改写结论。
3. **域偏移**：LAION-CLAP music_and_speech 预训练分布未必覆盖粤语口语/歌厅混响；系统性偏低的负 logit 中位可能是域适配问题，削弱与 PANNs 排序一致性。
4. **截断与时长**：脚本最多取 10s；短窗或歌唱后半段被截断时，CLAP 与整窗 PANNs 特征时间对齐不一致，会压低 Spearman。

## 方法备忘

- 设备：CPU；零样本提示：`a person singing` / `a person speaking`。
- 配对：仅 `clap_ok=1` 且与 quality CSV 按 `window_id` 内连接；本轮全成功，n_paired=4911。
- 未改 sqlite/音频；未改写 git 历史。

## 给 fyp 的 1:1 摘要草稿（简体）

ROUND-1 CLAP 全量 4911 窗已跑完。权重约 780MB（未触 2GB）。冒烟 20 窗通过后全量约 22 分钟完成，失败 0。Spearman(clap_sing, singing_prob)=**0.40**（达不到 0.7 互换门槛），故 **必须双轨抽样**。flag_sing=1（n=14）的 clap_sing 中位高于非标记，Mann–Whitney 单侧 p≈**0.039**，标记敏感性弱支持但样本很小。建议一.3 同时按 CLAP 与 PANNs 分层听辨，不要单用一轨。
