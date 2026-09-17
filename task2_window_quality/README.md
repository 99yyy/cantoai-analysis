# Task2：窗口质量列（music / singing / SNR / DNSMOS）

## 结论

1. **全量完成**：对 4911 个窗口 FLAC 写出四列质量特征，失败 0；未改 sqlite / `work/` 音频。
2. **墙钟**：全量三工具合计约 **1.38 h**（PANNs 0.17 h + Brouhaha 0.23 h + DNSMOS 0.97 h）。50 窗试跑外推 `est_hours=1.57`，与实跑接近。
3. **分布要点**：`music_prob` 双峰（近 0 与近 0.85）；`singing_prob` 极度右偏（中位 0.003）；`snr_db` 主峰约 5–20 dB，另有高 SNR 尾；`dnsmos_ovrl` 均值约 2.16（1–3.5）。
4. **与库内 `flag_sing` 对照**：14 个已标记窗的 `singing_prob` 均值仅 **0.080**（12/14 &lt; 0.2）；未标记但 `singing_prob≥0.5` 有 **13** 窗 → 标记与 PANNs 歌唱分数**几乎不对齐**，不宜直接用 0.2/0.5 阈值替换人工旗标。

## 支撑数字（可脚本重算）

```bash
# 摘要统计
python - <<'PY'
import pandas as pd
df = pd.read_csv("window_quality_with_flags.csv")
print(df[["music_prob","singing_prob","snr_db","dnsmos_ovrl"]].describe(percentiles=[.25,.5,.75]))
print("flag_sing=1 n=", int((df.flag_sing==1).sum()))
print("marked mean singing_prob", df.loc[df.flag_sing==1,"singing_prob"].mean())
print("unmarked >=0.5", int(((df.flag_sing==0)&(df.singing_prob>=0.5)).sum()))
print("marked <0.2", int(((df.flag_sing==1)&(df.singing_prob<0.2)).sum()))
PY
```

| 列 | mean | p25 | median | p75 |
|---|---:|---:|---:|---:|
| music_prob | 0.620 | 0.076 | 0.833 | 0.890 |
| singing_prob | 0.019 | 0.001 | 0.003 | 0.009 |
| snr_db | 22.48 | 6.95 | 12.82 | 28.09 |
| dnsmos_ovrl | 2.161 | 1.435 | 2.222 | 2.781 |

- 试跑：`trial_50_timing.json` → est_hours **1.567**；全量：`full_timing.json` → 实际 **1.376 h**，失败全 0。
- 工具定义见 `scripts/run_window_quality.py` 文档串（PANNs clipwise；Brouhaha 语音帧均值 SNR；DNSMOS 非个性化 OVRL）。
- 模型体积：Cnn14 ≈313 MB；brouhaha.onnx ≈16 MB；DNSMOS ≈1.4 MB（均 ≪ 2 GB）。

## singing 对照要点

| 现象 | 数量 | 产物 |
|---|---:|---|
| 库内 `flag_sing=1` | 14 | `singing_flag_marked_scores.csv` |
| 已标记但 singing_prob&lt;0.2 | 12/14 | 同上 |
| 未标记但 singing_prob≥0.5（漏检嫌疑） | 13 | `singing_miss_suspect_unmarked_ge0.5.csv` |
| 阈值扫描 | — | `singing_flag_contrast_by_threshold.csv` |

最高未标记例：`z0d7n9QxYiE_008`（0.704）、`MDNBEqwzQTA_009`（0.701）等。

图：`dist_histograms.png`、`dist_boxplots.png`、`singing_prob_vs_flag_sing.png`。

## 至少两条反对解释（为何不能草率改旗标）

1. **域偏移 / 标签语义不同**：PANNs 在 AudioSet（多为英语流行/合唱）上训；粤语口述、背景 BGM、念白腔可能被压低 `singing_prob`，而人工 `flag_sing` 可能按「像唱歌的段落」或剧情语义标，二者目标不一致。14 个标记窗最高分仅 0.26，说明**模型对已标窗系统性偏低**，不是简单阈值问题。
2. **高分未必是歌唱漏检**：`singing_prob≥0.5` 的未标记窗也可能是强情绪口语、叠声、配乐人声采样或短促哼唱；`music_prob` 双峰显示大量「有配乐的说话」，音乐≠歌唱。应用前需**人工抽听**高分未标记与低分已标记，再定阈值或校准。

## 产物清单

| 文件 | 说明 |
|---|---|
| `window_quality.csv` | 4911 行主表 |
| `window_quality_with_flags.csv` | 附 `flag_sing` |
| `trial_50_*.csv/json`、`TRIAL_NOTES.md` | 试跑 |
| `full_timing.json`、`summary_stats.json` | 全量计时与摘要 |
| `requirements.txt`、`scripts/` | 可复现；权重在 `models/`（gitignore） |
| `.venv/` | 本地环境（gitignore） |

## 硬性规则遵守

- 未写改 sqlite / work 音频。
- 仅 CPU；单模型均 &lt;2GB。
- est_hours≤12 后全量跑完。
