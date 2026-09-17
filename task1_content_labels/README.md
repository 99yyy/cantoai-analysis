# 任务 1：视频内容标签（content_type）

只读 SQLite 标题关键词打标，统计 A+B 层一致率，不做音频、不跑模型。

## 结论

1. **标题关键词可将语料分成五类**；主报告口径为 **tiers A+B**，一致率 = `jp_match ∈ {exact_default, exact_alt}`（与 `analysis/README.md` / PIPELINE 一致）。
2. **film 相关（PIPELINE 对照口径）与预期高度吻合**：八个核心词（李小龍/任劍輝/芳艷芬/林鳳/吳楚帆/石堅/謝賢/粵劇）命中 **119** 视频、A+B 音节 **40020（24.30%）**、一致率 **0.761**（95% CI **0.730–0.792**）。PIPELINE 所述「约 119 / 24% / 平均 0.761」可复现。
3. **打标优先级后的 `film_clip`（含补充词）为 125 视频、音节占比 26.39%、一致率 0.776**，略宽于 PIPELINE 八词口径；与 `contemporary` 的差异约 **−0.085**（95% CI −0.119…−0.051），支持「经典片相关材料一致率更低」的解释方向。
4. **parody / song** 样本量小但一致率更低（约 0.695 / 0.747），相对 contemporary 的 bootstrap 差值 CI 不含 0；**recitation** 一致率偏高（0.898），相对 contemporary 的差值 CI 含 0，不宜过度解读。

### 反对解释（需保留）

- 标题匹配只是代理，不能断定窗内是原声/片场音轨还是主讲人口播。
- 优先级把部分「影人+主题曲/恶搞」视频划出 `film_clip`（八词中有 6 条进 song/parody），故 `film_clip` ≠ PIPELINE 的 119。
- 一致率是模型–词典一致性，不是人工听辨正确率（见 PIPELINE）。

## 支撑数字（A+B；bootstrap：按 video_id 有放回，B=2000，seed=20260917，百分位 95% CI）

| content_type | 视频数 | 窗口数 | 音节数 | 音节占比 | 一致率 | 95% CI | Δ vs contemporary | Δ CI |
|---|---:|---:|---:|---:|---:|---|---:|---|
| parody | 7 | 29 | 1742 | 1.06% | 0.695 | 0.542–0.771 | −0.167 | −0.330…−0.093 |
| song | 12 | 67 | 2223 | 1.35% | 0.747 | 0.632–0.856 | −0.114 | −0.226…−0.009 |
| recitation | 15 | 68 | 1900 | 1.15% | 0.898 | 0.824–0.938 | +0.037 | −0.036…+0.079 |
| film_clip | 125 | 871 | 43457 | 26.39% | 0.776 | 0.743–0.807 | −0.085 | −0.119…−0.051 |
| contemporary | 408 | 3404 | 115371 | 70.05% | 0.861 | 0.850–0.872 | — | — |
| **film_related_core（PIPELINE）** | **119** | **827** | **40020** | **24.30%** | **0.761** | **0.730–0.792** | −0.099 vs 非 core | −0.134…−0.066 |

数字可由 `label_content_types.py` 重算；汇总见 `summary_by_content_type.csv`。

## 与预期对照

| 指标 | PIPELINE 预期 | 本任务（八词 core，无优先级重分类） | 判定 |
|---|---|---|---|
| 视频数 | ≈119 | 119 | 一致 |
| A+B 音节占比 | ≈24% | 24.30% | 一致 |
| 一致率 | ≈0.761 | 0.761 | 一致 |

`film_clip` 口径（优先级 + 补充词）更宽：125 视频 / 26.39% 音节 / 0.776；**报告「是否接近预期」应以八词 core 行为准**。

## 打标规则（脚本硬编码，冲突只归一类）

**优先级**：`parody` > `song` > `recitation` > `film_clip` > `contemporary`。

| 类 | 关键词（含必含项与补充） |
|---|---|
| parody | 惡搞、配音 |
| song | 主題曲、插曲、粵曲；补充：經典金曲、翻唱、清唱、獻唱、主唱、合唱 |
| recitation | 朗誦；补充：誦讀、朗讀（库内标题实际用后两者） |
| film_clip | 李小龍、任劍輝、芳艷芬、林鳳、吳楚帆、石堅、謝賢、粵劇；补充：粵語長片、粵語片、戲曲、銀幕、影星、白雪仙、新馬師曾、紅線女、唐滌生、夏夢、于素秋、張活游、白燕、紫羅蓮、林黛、嘉玲、李龍基、王青霞 |
| contemporary | 未命中以上任一类 |

**PIPELINE film 相关对照**：仅八词 `{李小龍,任劍輝,芳艷芬,林鳳,吳楚帆,石堅,謝賢,粵劇}` 标题命中（`film_related_core` 列），**不做优先级重分类**。

## 口径

- 数据：`/workspace/cantoai/corpus/dataset_v2/work/corpus.sqlite`（videos / windows / syllables）
- 主层：`syllables.tier ∈ {A,B}`；窗口数同层 `windows.tier`
- 一致率：音节级 `exact_default + exact_alt` 占比（音节加权）
- Bootstrap：对各类内 `video_id` 有放回重采样，合并音节后算一致率；B=2000；95% 百分位区间。相对 contemporary 的差值同法（两臂各自重采样）。`film_related_core` 行的 Δ 相对**非 core** 视频。

## 文件

- `label_content_types.py` — 可复算脚本
- `video_labels.csv` — 每视频标签与 A+B 计数
- `summary_by_content_type.csv` — 按类汇总 + CI
- `agreement_by_content_type.png` — 一致率±CI 与音节构成
- `requirements.txt` — 相关包版本（pip freeze）

```bash
/workspace/cantoai/.venv/bin/python analysis/task1_content_labels/label_content_types.py
```
