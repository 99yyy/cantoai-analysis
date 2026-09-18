# ROUND-2 · 抽样框遗漏（阶段1方法审本应拦下）

- 日期：2026-09-18
- 核实：`listening_sheet.csv` ⋈ `corpus.sqlite.windows`（`window_id=uid`）
- 判定：阶段1方法审**漏检**——契约未钉死「仅 tier A+B / 仅 lang=yue」抽样框，导致 32/200（16%）非 yue 且全 tier C 进入听辨样本（其中 film 23）。

## 核实数字

- 非 yue：zh 25 + en 7 = 32；tier 全 C
- 全库非 yue 均在 tier C（en 135 / ja 1 / zh 299）；非 yue ∩ A/B = 0
- 发布 dataset_v2 仅 A+B → 这 32 条不在发布集

## 处置（Tom 定）

- **不重抽、不换表**
- 阶段4：全集 + `lang=yue`（或 tier A+B）子集两套并报差异
- `lang` 不作口语真值；听感以 annotator 备注为准

## 对方法审的记录

此条应在阶段1以硬条件「抽样框 = 下游分析框（建议 A+B 或 lang=yue）」拦住；记入本文件供后续 ROUND 模板吸取。
