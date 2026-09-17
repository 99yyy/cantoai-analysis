# ROUND-2 阶段1 · 方法审（复审）

- 输入：`rounds/ROUND-2.md`（打回后修订版；计数 1/2）
- 判定：**通过**
- 对照：`review/ROUND-2/method.md` 首版硬条件 1–6

## 硬条件逐条复核

| # | 条件 | 复核 | 结果 |
|---|------|------|------|
| 1 | 钉死窗级 `film_flag` | 契约输入改为 `window_multilabel_flags.csv`；写明不用视频表；CLI `--flags-csv` | 满足 |
| 2 | 全库四分位 + 层定义 | 抽样前全量可配对窗；q1/q3 写入 `sample_manifest.json`；`both_high/both_low/panns_high_only/clap_high_only/mid` 表钉死；选定四分位交叉（非 3×3） | 满足 |
| 3 | `singing_rate` 可重算 | `mean(human_label=="singing")`，不含 mixed；`recitation_or_mixed_rate` 写死；已删「以唱为主」 | 满足 |
| 4 | `flag_sing` 强制规则 | 规则 A：`forced_in_quota: true`，计入 n_total=200；`forced_flag_sing_ids` | 满足 |
| 5 | CLI/产物键 | `--var-csv`；sheet/manifest/STATUS；manifest 键列表完整；`--summarize-labels` 预留且 metrics 键对预测 | 满足 |
| 6 | 冒烟门槛 | `--limit`/fixtures → `smoke_ok: true`；迷你 sheet ≥1 且全 `unset`；停止条件禁止冒烟前全量 | 满足 |

## advisory（不阻塞）

- Cloud Agent 按 Tom 指示 ≥04:20 HKT 再 launch；方法审不阻。
- n=200、film 配额重，H2/H3 检验力有限；保留效应量即可。
- 标签枚举含 `transcription_error`；与内容类冲突标 `mixed`+note，可接受。

## 结论

**通过。** 可进入阶段2（写 `scripts/build_listening_sheet.py`），但 **launch 不早于约 04:20 HKT**。预测数值门槛保持 `fffad051…` 冻结，不得再改三个不等式。
