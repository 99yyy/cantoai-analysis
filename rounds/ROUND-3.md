# ROUND-3：复算全部非音频结果（不重跑模型推断）

## 元数据

- 阶段：5（已结轮）
- backlog 条目：审计后复算；唱段旗标结论撤回；抽样框显式声明
- 执行角色：Cloud Agent（阶段 2 脚手架）+ 分析员（阶段 3 复算）+ 审稿员（方法审）；**音频员本轮不执行任何模型推断**
- 方法审打回计数：2/2
- 复核打回计数：0/2
- Cloud Agent launch 次数：1/2（本次阶段2脚手架）
- 预测仓库：`https://github.com/99yyy/cantoai-analysis`
- 预测 commit：`d6f1132a1fdfddffb36d6855e322580b22e9dc9c`（含冻结后的预测三不等式；必须早于任何结果 commit）
- 预测 commit 核验路径（clone 内已含对象，无需 fetch）：`/workspace/repos/cantoai-analysis` 与 `/tmp/cantoai-analysis-push`；命令：`git -C /workspace/repos/cantoai-analysis rev-parse --verify d6f1132a1fdfddffb36d6855e322580b22e9dc9c^{commit}`
- 结果 commit：`7fe0ccffa15d7f0cc8bdb0f9fdff04547f64bcdb`（晚于预测 `d6f1132`；merge-base --is-ancestor 通过）
- 执行 commit：`7fe0ccffa15d7f0cc8bdb0f9fdff04547f64bcdb`
- 合并目标 commit：
- 契约：`.cursor/rules/analysis-contract.mdc` 英文 v3，20 条，sha256 `461e8928597b1269be05088f3296663b896f1a5c4d264c2d7be3cf41ad5db3e5`，commit `228c78a`。旧中文版（`7865e108…`）作废。

## 本轮为何存在（五条已核实事实）

以下每条都可独立复核，来源写在括号里。

1. 发布出去的 `windows` 表 28 列**不含** `music_prob` / `singing_prob` / `snr_db` / `dnsmos_ovrl`。那四列只能外算，task2 的全量跑**不是**冗余劳动。（`PRAGMA table_info(windows)`）
2. `flag_sing=1` 全库仅 **14 条，全部在 tier C，tier A+B 为 0 条**。因此在发布集上该旗标恒为 0、不携带信息；task2 的「标记 vs 未标记」对比与 tier 完全共线，那个 `p≈0.011` 是一个披着旗标外衣的 tier 对比。（`select tier,count(*) from windows where flag_sing=1 group by tier`）
3. `singing_prob ≥ 0.5` 且 `flag_sing=0` 共 **13 条**，其中 **tier A 6 条、tier C 7 条**，但只来自 **6 个视频**。按契约第 14 条按 `video_id` 聚类，`G=6 < 10` → `ci_unreliable=1`。这 13 条只能作为**抽听候选清单**，不能支撑任何比率结论。
4. CLAP 只看每窗**前 10 秒**（`task_round1_clap_sing/scripts/run_clap_sing.py` 第 37 行 `CLAP_MAX_SECONDS = 10`、第 350 行 `audio = audio[:max_n]`）；task2 的 PANNs / Brouhaha / DNSMOS 读**整窗**（`load_mono` 无截断，PANNs 为 clip 级）。窗长中位 7.93 秒，4911 条中 **2142 条超过 10 秒**（A+B 内 2006 条），上述 13 条高唱段里 8 条超过 10 秒。两列同名 `singing_prob` 量的是不同跨度，按契约第 6 条**不得**出现在同一行或同一比较中。
5. 全库基数：4911 窗 / 567 视频 / tier A 3048、B 1391、C 472 / `sum(dur)=17.3 h`。总体只能表述为「本频道 567 个视频」，不得表述为「粤语」（契约第 19 条）。

## 问题（一句话，可被数据否定）

把抽样框显式声明（tier 白名单 + 排除订阅结尾样板 + 零宽时间戳单独计数）之后，既有三项主结论是否仍然成立？

## 假设

1. **H1（期间下降稳健）**：声明抽样框后，film 与 contemporary 的一致率差**减去基线期同一差值**，BH 校正后 `p < 0.05` 且方向不变。
2. **H2（SNR 不能解释）**：在 `snr_db > 15` 且 PANNs 整窗 `singing_prob < 0.2` 的子集上，声母 n-/ng-/gw- 的组间差减去基线差 `≤ −15pp`。此处 `singing_prob` **仅**来自 `task2_window_quality/window_quality_with_flags.csv`（PANNs 整窗）；**不**与 CLAP `clap_sing` 同表或同比较。
3. **H3（唱段影响可忽略稳健）**：剔除 PANNs 整窗 `singing_prob > 0.5` 的窗后，film 一致率变化满足 `abs(delta_pp) ≤ 0.5`。`singing_prob` 来源同 H2；**不**与 CLAP `clap_sing` 同表。

## 预测（每条假设成立时数据呈现的模式）

1. 若 H1：`analysis/ROUND-3/metrics/did_period.json` 中 `did` 与 `p_bh` 满足上式，且该行同时列出两组各自的值与其基线值。
2. 若 H2：`analysis/ROUND-3/metrics/did_highsnr_onset.json` 中 `did ≤ −0.15`。
3. 若 H3：`analysis/ROUND-3/metrics/singing_removal.json` 中 `abs(delta_pp) ≤ 0.5`（键 `delta_pp` 为剔除前后 film 一致率之差，单位百分点）。

**预测冻结规则**：上述三个不等式所在 commit 必须早于任何结果 commit。方法审通过后不得修改。

## 判据（哪张表哪一列）

- 一致率 := `n_match / n_judgeable`，`n_match` 为 `jp_match ∈ {exact_default, exact_alt}` 的音节数，`n_judgeable = n_total − n_empty_realized − n_dur_le_0`。四个计数全部写进输出（契约第 20 条）。
- **一律直接从 `jp_match` 计算，不读 `review_prior`**：该列把 `jp_match='none'` 与一致混同。
- 每条差值行必须同时给出两组各自的值与各自的基线值，供读者重算（契约第 13 条）。
- 每个比较行带 `comparison_id`，取自 `rounds/ROUND-3.yaml`，并给出 raw 与 BH 校正后的 p 值及 `m`（契约第 15 条）。

## 数据（范围、已知失效情形）

- 范围：tier A+B，4439 窗 / 567 视频。tier C 不进任何主结论。
- 已知失效，逐条在 `frame.yaml` 里写成谓词，剔除行数记入 `row_accounting`：
  - 零宽时间戳：`syllables.dur <= 0` 约 14.5%，单独计数，**默认不计为不一致**。
  - 订阅结尾样板：同一段结尾文本 512 条 `flag_boiler=0`（tier A 内 410 条）。本轮在 `frame.yaml` 以文本谓词排除，**不动 dataset repo**。
  - `review_prior` 语义缺陷：见上。
  - `flag_sing` 在 A+B 恒 0：**不得**用作分层变量或对照组定义（契约第 11、18 条）。
  - CLAP 与 PANNs 跨度不同：仅在 `dur <= 10` 的 2769 窗（A+B 内 2433 窗）可配对；其余窗两列不得同表比较。
  - `coverage` 为跨度比、可超过 1：不得当作 0–1 的比例使用。

## 工具（来源、为什么适用、无校准写未校准）

- **不重跑任何模型推断**。PANNs / Brouhaha / DNSMOS / CLAP / demucs 的既有分数原样复用。
- 复用的前提是补跨度列，且跨度**必须从脚本恢复、不得猜测**（契约第 2 条）：task2 三工具为整窗，`t0_s = windows.start`、`t1_s = windows.end`（由 `flac_path(video_id, idx)` 反推）；CLAP 为 `t0_s = windows.start`、`t1_s = start + min(10, dur)`。
- H2/H3 所用 `singing_prob` **钉死为** `task2_window_quality/window_quality_with_flags.csv` 的 PANNs 整窗列；绝对刻度**未校准**，本轮不据其下阈值结论，且不与 CLAP `clap_sing` 同表。

## 脚本契约

- 输入路径（CLI 或无默认值环境变量；契约第 18 条）。全部只读：
  - `--corpus-path` / `CORPUS_PATH`：`corpus.sqlite`（含 `videos` / `windows` / `syllables`；一致率从 `syllables.jp_match` 计算）
  - `--window-quality` / `WINDOW_QUALITY_CSV`：`task2_window_quality/window_quality_with_flags.csv`（本轮 H2/H3 的 `singing_prob`、`snr_db` 唯一来源；PANNs / Brouhaha / DNSMOS 整窗）
  - `--clap-sing` / `CLAP_SING_CSV`：`ROUND-1/window_clap_sing.csv`（**本轮 H2/H3 不读**；仅若日后配对跨度且 `dur<=10` 才允许与 PANNs 同表）
  - `--frame-file` / `FRAME_FILE`：`frame.yaml`
  - `--round-yaml` / `ROUND_YAML`：`rounds/ROUND-3.yaml`
- **禁止**调用任何推理入口：无 `run_clap*`、`run_*panns*`、demucs / Brouhaha / DNSMOS 推理脚本；只复用既有 CSV 分数。
- 输出：`checks.json`、`manifest.json`、上列三个 metrics JSON，各带 `fixtures/schemas/` 下的 schema。
- 一条命令可重跑：

```bash
python -m src.round3 \
  --corpus-path "$CORPUS_PATH" \
  --window-quality "$WINDOW_QUALITY_CSV" \
  --frame-file "$FRAME_FILE" \
  --round-yaml "$ROUND_YAML" \
  --out-dir "$OUT_DIR"
```

## 阶段顺序（本轮为硬顺序，不得合并）

- **阶段 2（Cloud Agent，先做，且这个 PR 不得包含任何统计数字）**：建 `scripts/contract_check.py`、`frame.yaml`、`sql/*.sql`、`fixtures/manifest.schema.json`、`fixtures/schemas/`、`tests/mutations/`，并写出 `checks.json`。`frame.yaml` 至少声明：tier 白名单、上列每条排除谓词、`expected_rows` / `expected_rows_tol` / `expected_rows_source`、`measure_columns`、`status_codes`、`min_judgeable: 200`（本项目约定，非定理）、`groups.treatment` 与 `groups.control` 各自的显式谓词。
- **阶段 3（分析员）**：阶段 2 合入后才复算。
- **音频员**：本轮只补 `t0_s` / `t1_s` 两列，不跑模型。

这个顺序的用途是：如果阶段 2 的 PR 能把契约第 1–4 条落成能跑的东西，说明规则真的被读进去了；如果不能，我们只损失一个不含任何数字的小 PR。

## 撤回记录

关于人工唱段旗标与 `singing_prob` 刻度是否对齐的既有表述，本轮撤回：该对比的两组与 tier 完全共线，在发布集上旗标恒为 0，故该问题在发布集上不可判定。原先据此提出的「抽听后再定阈值」这一动作保留，但依据改为上文第 3 点的 13 条候选窗（其中 6 条在发布集内），并明确其聚类视频数为 6、按本项目约定标记为区间不可靠。

## 预算

- 消息：12
- Cloud Agent：2 次
- 执行：12 小时

## 停止条件

- 仓库根出现 `STOP` 文件。
- 方法审两次打回。
- 阶段 2 的 PR 出现任何统计数字。

## 争议记录

- 2026-09-18 阶段1方法审 **改**（1/2）：见 `review/ROUND-3/method.md` 硬条件 1–5。
- 2026-09-18 阶段1复审 **改**（2/2）：仅硬条件5——审稿员旧 clone 无 `d6f1132` 对象；已刷新 `/tmp/cantoai-analysis-push` 与 `/workspace/repos/cantoai-analysis`（GitHub main 已含该对象）。

-
- 2026-09-18 阶段1终审 **通过**：硬条件5 rev-parse 在 `/workspace/repos/cantoai-analysis` 与 `/tmp/cantoai-analysis-push` 均为 0；可进阶段2。
- 2026-09-18 阶段2脚手架合入 main（PR #10，merge 含 `2929cec`）：无统计数字；预测 commit 仍为 `d6f1132`。

## 验证记录

- GitHub 例程是否触发：**是**（pr-merged PR #10，https://github.com/99yyy/cantoai-analysis/pull/10 ，分支 `cursor/round3-stage2-scaffold-8178`，标题 ROUND-3 stage 2: analysis-contract scaffolding (no stats)；merge `9f9928b` / scaffold `2929cec`；CST 2026-09-18 ≈14:48）
- 2026-09-18 阶段3完成：c1 rejects_H1（did≈−0.004 p_bh≈0.857）；c2 rejects_H2（did≈−0.065，未达 −0.15）；c3 supports_H3（delta_pp≈+0.05）；结果 commit `7fe0ccf`。进阶段4复核。
- 2026-09-18 阶段4复核 **通过**（`review/ROUND-3/result.md`）；阶段5裁决结轮。
