# ROUND-3 阶段4 · 复核

- 输入：`analysis/ROUND-3/`（README + `metrics/*.json` + `STATUS.json`）+ `rounds/ROUND-3.md`
- 预测 commit：`d6f1132a1fdfddffb36d6855e322580b22e9dc9c`（2026-09-18 14:17 +0800）
- 结果 commit：`7fe0ccffa15d7f0cc8bdb0f9fdff04547f64bcdb`（2026-09-18 14:55 +0800）
- 判定：**通过**

## 1. 预测早于结果

| 检查 | 结果 |
|------|------|
| `git -C /workspace/repos/cantoai-analysis merge-base --is-ancestor d6f1132 7fe0ccf` | 退出码 **0** |
| 预测树内三不等式 | 仍为 H1 `p_bh<0.05` 且方向不变；H2 `did≤−0.15`；H3 `abs(delta_pp)≤0.5` |
| 结果未回写预测 | 结果为预测后代；未发现事后改预测 |

## 2. 自写最小查询重算（禁止 import / 跑分析员脚本）

工作目录证据：`review/ROUND-3/recalc_key.json`。数据：`corpus.sqlite` + `task2_window_quality/window_quality_with_flags.csv` + `task3_multilabel_flags/video_multilabel_flags.csv`；框：tier A+B、排除订阅样板文本、`film_flag=1` / `contemporary_only=1`；一致率 = `jp_match∈{exact_default,exact_alt}` / 可判定（非空 realized 且 `dur>0`）；基线期 `upload_date < '2025-01-01'`。

| 比较 | 关键量 | 重算 | 报告 | 一致 |
|------|--------|------|------|------|
| c1 / H1 | `did` | −0.004224756746657676 | −0.004224756746657676 | 是（至浮点） |
| c1 | `n_judgeable` / `n_match` / `n_total` / `n_empty` / `n_dur_le_0` | 132593 / 112636 / 156302 / 2114 / 21595 | 同左 | 是 |
| c1 | 四率 film/cont × pre/post | 与 JSON 四键完全一致 | 同左 | 是 |
| c2 / H2 | `did`（onset 含 `kw`，同 `sql/c2_highsnr_onset.sql`） | −0.06456606643970009 | −0.06456606643970009 | 是 |
| c2 | `n_judgeable` | 3364 | 3364 | 是 |
| c3 / H3 | `delta_pp`；before/after | 0.05018951647176584；0.79495… / 0.79545… | 同左 | 是 |

对照预测三不等式：

- H1：`did≈−0.004`，报告 `p_bh≈0.857` → **不满足** `p_bh<0.05` → `rejects_H1` 成立。
- H2：`did≈−0.065` **不满足** `≤−0.15` → `rejects_H2` 成立。
- H3：`abs(0.050…)≤0.5` → `supports_H3` 成立。

未独立重跑 video 聚类 bootstrap 的 `p_bh`（advisory）：H1 否决由近零 `did` 已充分；`p_bh` 不作本轮硬门槛重算对象。

## 3. 替代解释（≥2；结论可能仍错）

1. **共同时间趋势 / 切点伪影**：film 与 contemporary 在 post 期一致率几乎同幅下降（约 −8pp），DID≈0 也可能是「频道整体变难标」或 `2025-01-01` 切点与内容批次共线，而非「组间差本身不稳健」的唯一解释。
2. **H2 子集仍混杂语域**：`snr_db>15` 且 `singing_prob<0.2` 压低唱段噪声后，film 对白 vs 当代口播的语速/口音/脚本差异仍可压低 onset 一致率；`did≈−6.5pp` 未达 −15pp 阈值，也可能是阈值过严或 onset 集合（含 `kw`）稀释效应，而非「SNR/唱段可解释差距」被证伪。
3. **H3 剔除量极小**：剔除 `singing_prob>0.5` 后可判定音节仅少约 42（36679→36637），`delta_pp≈+0.05` 在阈值内更像**功效不足**，不能强解为「唱段对 film 一致率可忽略」；PANNs 绝对刻度本轮未校准，阈值 0.5 本身可错。

## 4. Advisory（不计打回）

- `rounds/ROUND-3.md` / 部分 README 措辞写 onset∈{n,ng,gw}，但 `ROUND-3.yaml` 与 `sql/c2_highsnr_onset.sql` 含 `kw`；报告数字与**含 kw** 契约一致。若对外只写 n/ng/gw，应改文案或改 SQL 后重跑（当前不挡通过）。

## 5. 结论

**通过。** 可向用户汇报：声明抽样框后，H1/H2 预测不等式不成立，H3 成立；关键点估计均可由独立音节级查询复现。无必须满足的打回条件。
