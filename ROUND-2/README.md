# ROUND-2 listening sheet（待 Tom 标注）

- `listening_sheet.csv`：200 窗，`human_label` 初值为 `unset`
- 配额：film 160 / contemporary 40；`flag_sing=1` 强制 14（计入 200）；五层各 40
- 种子：`20260918`（见 `sample_manifest.json`）

## 标注

把 `human_label` 改成下列之一（每行只选一个主类）：

`dialogue` | `singing` | `recitation` | `mixed` | `transcription_error`

可选在 `annotator_note` 写备注。不要改 `window_id` / 分数列 / `stratum`。

标注完成后通知 fyp；再跑 `--summarize-labels` 与阶段4复核。

## 部分标注（Tom 2026-09-18）

不必标满 200。工具按 stratum 轮流出题，已标部分五层均衡。阶段4只统计非 unset；按层算后用设计配额 40 加权；附按视频 bootstrap 95% CI 与每层 n；不够则写明还需多少条。`annotator_note` 含 `saw_meta` 的行单独计数。
