# ROUND-3 复算结果（分析员）

抽样框：tier A+B，排除订阅结尾样板文本；一致率仅从 `jp_match ∈ {exact_default,exact_alt}`；`n_judgeable = n_total − n_empty_realized − n_dur_le_0`。不读 `review_prior`，不用 `flag_sing` 分层。H2/H3 的 `singing_prob`/`snr_db` 仅来自 `task2_window_quality/window_quality_with_flags.csv`（PANNs 整窗），不与 CLAP 同表。

运行模式：全量 corpus。

## 结论对照预测（commit d6f1132）

| 比较 | 预测 | 观测 | 判定 |
|---|---|---|---|
| c1_period_drop (H1) | p_bh<0.05 且方向不变 | did=-0.004225, p_bh=0.857139 | rejects_H1 |
| c2_highsnr_onset_residual (H2) | did ≤ −0.15 | did=-0.064566, p_bh=0.588133 | rejects_H2 |
| c3_singing_removal (H3) | abs(delta_pp)≤0.5 | delta_pp=0.050190, p_bh=0.574721 | supports_H3 |

## 支撑数字

### H1 / c1_period_drop

- did = (film_post − cont_post) − (film_pre − cont_pre) = -0.004225
- film_post=0.753545, film_pre=0.834165
- cont_post=0.805704, cont_pre=0.882099
- p_raw=0.857139, p_bh=0.857139, m=3
- n_judgeable=132593, G_h=535, ci_unreliable=0

### H2 / c2_highsnr_onset_residual

- 子集：snr_db>15 且 singing_prob<0.2 且 onset∈{n,ng,gw}
- did=-0.064566（阈值 ≤ −0.15）
- film_post=0.618736, film_pre=0.749235
- cont_post=0.863248, cont_pre=0.929181
- p_raw=0.392088, p_bh=0.588133
- n_judgeable=3364, G_h=382

### H3 / c3_singing_removal

- film 剔除 singing_prob>0.5 前后：before=0.794951, after=0.795453
- delta_pp=0.050190（百分点；阈值 abs≤0.5）
- p_raw=0.191574, p_bh=0.574721
- n_judgeable=36637, G_h=130

## 反对解释 / 边界

- 总体仅表述为本频道视频集合（frame.yaml `n_videos`），不得外推为「粤语」。
- 聚类至 `video_id`；`G_h<10` 时 `ci_unreliable=1` 且结论 inconclusive。
- 冒烟夹具若无 post-2025 单元，DID 可为 null，结论 inconclusive，不否定全量结果。
- 音频跨度溯源见 `metrics/span_provenance_summary.json`（若存在）；本复算不读 CLAP。

## 重算命令

```bash
cd /workspace/cantoai/analysis
python -m src.round3 \
  --corpus-path "$CORPUS_PATH" \
  --window-quality task2_window_quality/window_quality_with_flags.csv \
  --flags-csv task3_multilabel_flags/video_multilabel_flags.csv \
  --frame-file frame.yaml \
  --round-yaml rounds/ROUND-3.yaml \
  --sql-dir sql \
  --out-dir ROUND-3
```
