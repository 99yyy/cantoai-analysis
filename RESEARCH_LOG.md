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

见下「ROUND-3 结轮」矛盾节；旧 REPORT 期间差/SNR-onset 残差阈值需按 DID 口径重读。

## 2026-09-17 一.1 收口

- **结果**：htdemucs → `var_db` 全量 4911/4911，失败 0；墙钟 ≈4.5h；权重 ≈80MB。
- **关键数字**：`var_db` 均值 ≈17.98，中位 ≈12.72（见 `task_calib_demucs_var/artifacts/full_stats.json`）。
- **仓库**：结果 commit `42f5ae9`（含 Separator 单例本地补丁说明）。
- **审稿**：通过；`review/calib-1.1-result.md`（独立重算：4911 全覆盖、var_db 最大偏差 5e-5）。工作区 commit `4804b53` ≡ 分析库 `42f5ae9`。
- **下一题**：ROUND-1 = 一.2 CLAP `clap_sing` 与 PANNs `singing_prob` 对照。

## 2026-09-18 ROUND-1 结轮（一.2 CLAP vs PANNs）

- **问题**：全窗上 `clap_sing` 与 PANNs `singing_prob` 是否可互换（ρ≥0.7），且对 `flag_sing=1` 敏感。
- **结果**：Spearman **ρ≈0.400**（n=4911）→ **H1 不成立**；`flag_sing` 中位差方向对且 MW p≈0.039（n_flag1=14）→ **H2 弱支持**；ρ&lt;0.5 → H3 部分支持。
- **裁决**：CLAP 与 PANNs **不能互相替代**；一.3 听辨抽样必须 **双轨分层**（同时按 `clap_sing` 与 `singing_prob`）。
- **产物**：`ROUND-1/` @ `4eab466`；审稿 `review/ROUND-1/result.md` 通过。
- **验证**：CloudAgent.launch 完成会唤醒（含 error）；GitHub `pr-merged` 例程会唤醒；`pr-opened` 本轮未观测。
- **下一题**：ROUND-2 = 一.3 人工听辨 200 窗 + `listening_sheet`。

### 矛盾

- 与旧 REPORT「唱段/C 可忽略、单一 singing_prob 阈值即可」叙事冲突：未校准的 PANNs 与 CLAP 仅中等相关，阈值与分层不能只靠一侧分数。记入矛盾，不自动停回路。

## 2026-09-18 ROUND-3 结轮（审计后复算）

- **问题**：声明抽样框（tier A+B + 排除订阅样板 + 零宽单独计数）后，既有三项主结论是否仍成立？
- **预测冻结**：`d6f1132`；结果：`7fe0ccf`（祖先关系已核）。
- **结果**（音节级 DID / 剔除差；审稿独立重算至浮点一致）：
  - **H1 否**：期间差分 `did≈−0.004`，`p_bh≈0.857` → film/contemporary 缺口相对 pre-2025 **不稳健**（两侧 post 期几乎同幅下降）。
  - **H2 否**：高 SNR + 低 singing_prob 子集上 onset 残差 `did≈−0.065`，**未达** `≤−0.15` 阈值（post 原始缺口仍大，但减基线后不够）。
  - **H3 是**：剔除 PANNs `singing_prob>0.5` 后 film `delta_pp≈+0.05`，`abs≤0.5`（剔除量极小，功效有限——审稿 advisory）。
- **方法要点**：不重跑模型；`singing_prob` 钉死 PANNs 整窗 CSV；不与 CLAP 同表；一致率只从 `jp_match`；`flag_sing`/`review_prior` 禁用分层。
- **审稿**：阶段1 经 2 次打回后终审通过；阶段4 `review/ROUND-3/result.md` **通过**（0 打回）。
- **脚手架**：PR #10 合入（仅契约产物，无统计数字）。
- **下一题**：不新开轮打断 ROUND-2；等听辨标注推进。其后 backlog #4 SenseVoice。

### 矛盾

- 与旧 REPORT「期间 film 低分稳健 / SNR 不能解释的声母残差 ≥15pp / 唱段可忽略」叙事部分冲突：在显式抽样框 + pre-2025 DID 下，**期间组间差与高SNR onset 残差两条均未过本轮阈值**；唱段剔除影响仍小。记入矛盾，不自动停回路。ROUND-2 人工听辨与后续转写一致字分析仍必要。

## 2026-09-18 ROUND-3 过程缺陷（不重跑）

ROUND-3 三个 metrics 与审稿重算一致，**结论保留**。过程缺陷两条，记入而不重开 ROUND-3：

1. **阶段 3 直推 main、无 CI**：分析员在共享机器上直接推送结果 commit（`7fe0ccf`），当时缺少强制 PR + 三检查闸门。
2. **`src/merge.py` 同 commit 旁路**：同一结果 commit 为 `checked_merge` 增加 `enforce_expected=False`，并为 `left_attach` 提供不经 `expected_rows` 门的路径，掏空契约第 9 条。

处置：LOOP v2（分支保护 + `data/corpus_v2.sqlite` + 盲配对）；**ROUND-4** 第 1 波固定删除 `enforce_expected`、强制 `left_attach` 字面量、`contract_check` 四条新规则。

## 2026-09-18 ROUND-4 结轮

- **问题**：删 `enforce_expected`、强制 `left_attach` 从 `frame.yaml: joins` 取字面量、钉死语料 sha256 后，三检查是否全绿且与 inputs 一致？
- **预测冻结**：`d50e2da`；结果：`8533d3c`（impl_a #27）；复核：`4e2614b`（#28 PASS）。
- **结果**：H1/H2/H3 均成立；`enforce_expected` 已无；`pd.merge(`=1；sha256=`2bd618ba…` 与 frame 一致；joins 字面量与语料计数一致（4439/567）。
- **过程**：方法审打回 1/2（预测基线误写）后复审通过；wave1 tests #25 + impl_a #27；impl_b #26 红后关闭；无 comparison 波。
- **下一题**：ROUND-2 听辨继续；其后 backlog SenseVoice。

