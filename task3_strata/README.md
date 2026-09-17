# Task3 分层假设检验（film vs contemporary）

对照假设：**A 劣化/SNR**、**B 旧读音（n-/ng-/gw- 等）**、**C 唱段**。  
口径：音节加权一致率 `agree_syl`（`jp_match ∈ {exact_default, exact_alt}`）与视频中位一致率；bootstrap 按视频重采样，B=2000，seed=0。  
子集：`film_flag=1` vs `contemporary_only=1`（tier A+B）。

## 结论摘要

| 假设 | 判定 | 关键数字（音节加权） |
|------|------|----------------------|
| **A 劣化/SNR** | **部分支持，但非单纯“SNR 分布更差”** | 总体 film 77.55% vs contemporary 86.14%（Δ=**−8.5806pp**）。SNR 分箱内差距大（&lt;5 dB：53.2% vs 76.8%；&gt;20 dB：68.7% vs 89.5%）。**Oaxaca（主报：film 权重作率效应参照）**：箱内率效应 **−8.2647pp**，组成效应 **−0.3159pp**（和=Δ）。对照（当代权重）：率 **−10.0319pp**，组成 **+1.4513pp**。film 一致率**不随 SNR 单调上升**（10–15 dB 峰值 82.8%，&gt;20 dB 反降至 68.7%）。 |
| **B 旧读音** | **支持（高 SNR 残差主导证据）** | `snr_db>15` 且口白（`singing_prob<0.2`）下 n-/ng-/gw-：film **63.96%** vs contemporary **91.30%**（Δ≈**−27.3pp**；n=1035 vs 3461）。声母全量：n- −14.4pp、ng- −15.1pp、gw-/kw- −6.8pp。Tone1→4/6：film 6.39% vs cont 3.73%。 |
| **C 唱段** | **不支持** | 去掉 `singing_prob>0.5` 后 film：77.55% → 77.61%，**回升仅 +0.057pp**；高唱段音节极少（film n=55）。 |

**归因谁主导：** 总体缺口主要来自 **各 SNR 箱内的一致率差（率效应 / 与 A 相关的质量·域交互）**，而非 film SNR 组成更差（组成效应接近 0 或符号相反，见下节）。在控制高 SNR + 口白后，**B（旧读/声母）解释最大残差**。**C 可忽略。**  
对 **task4**：主损**不能**简单判为“纯 SNR 驱动、提 SNR 即可”；高 SNR 下 n-/ng-/gw- 仍大幅落后，需同时考虑音系/词典口径与域偏移。

## Oaxaca–Kitagawa SNR 双折分解

定义（film − contemporary，比例尺度）：

- \(R_f=\sum_b w_f^{(b)} r_f^{(b)}\)，\(R_c=\sum_b w_c^{(b)} r_c^{(b)}\)，\(\Delta=R_f-R_c\)
- 权重 \(w\) = 该子集在 SNR 箱内的音节份额；率 \(r\) = 箱内 `agree_syl`

由 `agreement_by_snr.csv` 重算（脚本断言 `|rate+composition−Δ|<1e-9`）：

| 量 | 数值 |
|----|------|
| \(R_f\) | 0.775545 |
| \(R_c\) | 0.861352 |
| \(\Delta\) | **−0.085806（−8.5806pp）** |

### 主报：film 权重作率效应参照

\[
\text{rate}=\sum_b w_f^{(b)}(r_f^{(b)}-r_c^{(b)}),\quad
\text{composition}=\sum_b r_c^{(b)}(w_f^{(b)}-w_c^{(b)})
\]

| 成分 | 比例 | pp |
|------|------|-----|
| 箱内率效应 (rate) | −0.082647 | **−8.2647** |
| 组成效应 (composition) | −0.003159 | **−0.3159** |
| 和 | −0.085806 | **−8.5806**（=Δ） |

### 对照：当代权重作率效应参照

\[
\text{rate}=\sum_b w_c^{(b)}(r_f^{(b)}-r_c^{(b)}),\quad
\text{composition}=\sum_b r_f^{(b)}(w_f^{(b)}-w_c^{(b)})
\]

| 成分 | 比例 | pp |
|------|------|-----|
| 箱内率效应 (rate) | −0.100319 | **−10.0319** |
| 组成效应 (composition) | +0.014513 | **+1.4513** |
| 和 | −0.085806 | **−8.5806**（=Δ） |

**读数：** 两套分解均表明 **率效应主导**；当代权重下组成甚至为 **正**（film 的 SNR 份额相对有利），与“film 只是 SNR 更差”的单纯组成叙事不符。  
**勘误：** 旧版 README 将 1.45 / 8.26 的符号与配对写反（误写「组成 −1.45pp / 箱内 +8.26pp」且和≠Δ）；现以脚本 `oaxaca_snr_decompose.py` 为准。

产出：`oaxaca_snr.csv`（两套方案）、`oaxaca_snr_by_bin.csv`（主报按箱贡献）。

## 去掉 singing_prob>0.5 后 film 一致率回升

来源：`summary_contrast.csv`

| 口径 | 数值 |
|------|------|
| film_all | 0.775545（n_syl=45341，n_vid=130） |
| film_no_high_singing（≤0.5） | 0.776112（n_syl=45286） |
| **film_singing_removal_delta** | **+0.000567（约 +0.057pp）** |
| 视频中位回升 | 0.0（中位不变） |

## snr>15 电影口白里 n-/ng-/gw- vs contemporary

来源：`summary_contrast.csv`（电影口白 = film 且 `singing_prob<0.2`，再限 `snr_db>15`，声母 ∈ {n-, ng-, gw-}）

| 对比项 | agree_syl | 95% CI | n_syllables | n_videos |
|--------|-----------|--------|-------------|----------|
| film_dialogue_highsnr_n_ng_gw | **0.639614** | [0.569, 0.730] | 1035 | 88 |
| contemporary_highsnr_n_ng_gw | **0.913031** | [0.893, 0.931] | 3461 | 309 |
| 差距 | **−0.2734** | | | |

## 反对解释（至少两条）

1. **SNR 估计/混杂，而非真实清晰度**：film 在 &gt;20 dB 箱一致率反而最低，暗示 Brouhaha `snr_db` 可能与配音、后期、音乐床等混杂；箱内差距不一定等于“噪声导致识别差”。
2. **域/文本与标注口径，而非单纯旧读**：电影台词书面语、专名、文言色彩更重；`jp_default` 与模型实现音系口径不一致时，会在 n-/ng-/gw- 等声母上放大“假旧读”缺口（词典默认读 vs 口语实现）。
3. **视频级标签粗糙**：`film_flag` 为视频级关键词启发式，片内可混杂预告、访谈、主题曲；虽唱段过滤后几乎无回升，但仍可能有未建模内容类型偏倚。

## 产出文件

路径前缀：`/workspace/cantoai/analysis/task3_strata/`

- `summary_contrast.csv` — A/B/C 汇总对比
- `agreement_by_snr.csv` / `agreement_by_singing.csv` / `agreement_by_onset.csv`
- `agreement_by_coda.csv` / `agreement_by_tone.csv` / `agreement_by_rate.csv`
- `tone1_confusion.csv`
- `oaxaca_snr.csv` / `oaxaca_snr_by_bin.csv` — SNR Kitagawa–Oaxaca 分解
- **图：**
  - `fig_overall_film_vs_contemporary.png` — 总体 film vs contemporary（音节加权 + 视频中位，含 CI）
  - `fig_agreement_by_snr.png` — SNR 分箱对比
  - `fig_agreement_by_singing.png` — singing_prob 分箱对比
  - `fig_highsnr_dialogue_n_ng_gw.png` — 高 SNR 口白 n-/ng-/gw-
- `oaxaca_snr_decompose.py` / `plot_strata.py` / `requirements.txt`
- `_sample_out/` — 样例自检产出
- `_full_run.log` — 全量运行日志（wall ≈ 4s，exit 0）

主分层脚本副本：`/workspace/cantoai/analysis/task3_hypothesis_strata/scripts/`  
依赖亦可参考：`task3_hypothesis_strata/requirements.txt`（本目录 `requirements.txt` 另含 matplotlib）。

## 脚本复算命令

```bash
# --- Oaxaca（从已有 agreement_by_snr.csv；不读音频）---
/workspace/cantoai/.venv/bin/python \
  /workspace/cantoai/analysis/task3_strata/oaxaca_snr_decompose.py \
  --csv /workspace/cantoai/analysis/task3_strata/agreement_by_snr.csv \
  --out /workspace/cantoai/analysis/task3_strata/oaxaca_snr.csv

# --- 分层图（从现有 CSV）---
/workspace/cantoai/.venv/bin/python \
  /workspace/cantoai/analysis/task3_strata/plot_strata.py \
  --dir /workspace/cantoai/analysis/task3_strata

# --- 样例自检（主分层脚本）---
/workspace/cantoai/.venv/bin/python \
  /workspace/cantoai/analysis/task3_hypothesis_strata/scripts/run_hypothesis_strata.py \
  --db /workspace/cantoai/analysis/fixtures/sample.sqlite \
  --quality /workspace/cantoai/analysis/fixtures/sample_window_quality.csv \
  --multilabel /workspace/cantoai/analysis/task3_multilabel_flags/video_multilabel_flags.csv \
  --out /workspace/cantoai/analysis/task3_strata/_sample_out \
  --seed 0 --bootstrap 200

/workspace/cantoai/.venv/bin/python \
  /workspace/cantoai/analysis/task3_hypothesis_strata/scripts/check_sample_outputs.py \
  --out /workspace/cantoai/analysis/task3_strata/_sample_out

/workspace/cantoai/.venv/bin/python \
  /workspace/cantoai/analysis/task3_hypothesis_strata/scripts/test_jyutping_parse.py

# --- 全库分层表（bootstrap 2000；其后可再跑 Oaxaca/plots）---
/workspace/cantoai/.venv/bin/python \
  /workspace/cantoai/analysis/task3_hypothesis_strata/scripts/run_hypothesis_strata.py \
  --db /workspace/cantoai/corpus/dataset_v2/work/corpus.sqlite \
  --quality /workspace/cantoai/analysis/task2_window_quality/window_quality.csv \
  --multilabel /workspace/cantoai/analysis/task3_multilabel_flags/video_multilabel_flags.csv \
  --out /workspace/cantoai/analysis/task3_strata \
  --seed 0 --bootstrap 2000
```

## 运行记录

- 样例自检：`check_sample_outputs.py` PASS；`test_jyutping_parse.py` 14 tests OK
- 全量：Videos 567 / Windows 4439 / Syllables 164693；film 45341 syl / 130 vid；contemporary 115371 syl / 407 vid
- wall time ≈ **4 s**（HKT），exit code **0**，bootstrap=2000，seed=0
- Oaxaca + 四图：`oaxaca_snr_decompose.py` / `plot_strata.py` 已本地跑通（断言通过）
