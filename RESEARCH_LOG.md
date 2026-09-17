# RESEARCH_LOG

## 2026-09-17 前：任务 1–5 与 REPORT 否决

### 已完成（旧流程）

- **任务 1**：视频内容标签 → `task1_content_labels/`（后改为多标签 `film_flag` / `song_flag` / `parody_flag` / `recitation_flag`）。
- **任务 2**：窗级质量 → `task2_window_quality/`（`music_prob`、`singing_prob`、`snr_db`、`dnsmos_ovrl` 等）。
- **任务 3**：分层假设与 Oaxaca SNR 分解 → `task3_strata/` 等；音节加权 + 视频中位数双口径，附按视频 bootstrap 95% CI。
- **任务 4**：人声分离诊断 — **未做**（任务 3 未把主损归因于单纯 SNR）。
- **任务 5**：总报告 → `REPORT.md`（film vs contemporary 约 −8.58pp；C 唱段可忽略；A 纯 SNR 组成约 4%；箱内率差主导且高 SNR 口白 n-/ng-/gw- 残差指向 B）。

### REPORT.md 结论不采纳的原因

进入「校准—重测—重写」，不采纳原 REPORT 归因口径，主要因：

1. **主音乐床指标不可靠**：Brouhaha `snr_db` 与配音/后期/音乐床混杂；film 在高 SNR 箱一致率反而更差，不宜继续以 SNR 为主指标。
2. **唱段刻度未校准**：`singing_prob` / `flag_sing` 未与人工听辨对齐，C 成因的排除力度不足。
3. **转写误差未隔离**：一致率缺口可能混有 ASR/转写错误，需 SenseVoice（+可选 Qwen3）与逐字投票后再测。
4. **归因方法**：弃用 Oaxaca 份额叙事；改用 glmer/GEE 等标准混合效应/边缘模型，并在转写一致子集上复测。

### 当前主线

- 校准一.1：htdemucs → `var_db`（进行中）。
- 其后按 `LOOP.md` 开 ROUND，不再沿用旧任务编号派单。

### 矛盾

（尚无。与旧 REPORT 冲突时在此追加，不自动停回路。）

## 2026-09-17 一.1 收口

- **结果**：htdemucs → `var_db` 全量 4911/4911，失败 0；墙钟 ≈4.5h；权重 ≈80MB。
- **关键数字**：`var_db` 均值 ≈17.98，中位 ≈12.72（见 `task_calib_demucs_var/artifacts/full_stats.json`）。
- **仓库**：结果 commit `42f5ae9`（含 Separator 单例本地补丁说明）。
- **审稿**：通过；`review/calib-1.1-result.md`（独立重算：4911 全覆盖、var_db 最大偏差 5e-5）。工作区 commit `4804b53` ≡ 分析库 `42f5ae9`。
- **下一题**：ROUND-1 = 一.2 CLAP `clap_sing` 与 PANNs `singing_prob` 对照。

