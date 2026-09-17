# 任务3 预备：多标签内容 flags（非互斥）

本目录在**分层检验 / 一致率对比之前**，先按视频标题产出多标签 flags。  
**本次不做**分层检验、不做与任务1互斥标签的一致率对比；等任务2全量 `singing_prob` 审过后再做。

## 数据来源

| 项 | 路径 |
|---|---|
| 语料库（只读） | `/workspace/cantoai/corpus/dataset_v2/work/corpus.sqlite` |
| 关键词定义 | 复用 `analysis/task1_content_labels/label_content_types.py` 中的 `KEYWORDS` / `FILM_RELATED_CORE` |
| singing_prob（可选左连接） | 若存在则合并：`task2_window_quality/window_quality.csv`（全量，优先）、`trial_50_quality*.csv`、`artifacts/smoke*.csv` |

当前运行时：**全量 `window_quality.csv` 尚未交付**；仅合并到任务2试跑/冒烟窗的 `singing_prob`（约 51/4911 窗有值）。无 `singing_prob` 的窗不编造该列，也不编造 `dialogue_film`。

## 与任务1互斥标签的差异

任务1用**互斥优先级**给每个视频一个 `content_type`：

`parody > song > recitation > film_clip > contemporary`

本任务**不用**该优先级。同一视频可同时命中多类，对应 flag 可同时为 1。  
例如标题同时含「主唱」与「李小龍」时：`song_flag=1` 且 `film_flag=1`（任务1会只标成 `song`）。

`film_related_core` 与任务1一致：仅 PIPELINE 八词子集，与 `film_flag`（完整 film_clip 词表）独立，可并存。

## 多标签规则（视频级，标题子串匹配，繁体关键词与任务1相同）

对 `videos.title` 做子串包含匹配：

| 列 | 规则 |
|---|---|
| `parody_flag` | 命中 parody 关键词（惡搞、配音） |
| `song_flag` | 命中 song 关键词（主題曲、插曲、粵曲、經典金曲、翻唱、清唱、獻唱、主唱、合唱） |
| `recitation_flag` | 命中 recitation 关键词（朗誦、誦讀、朗讀） |
| `film_flag` | 命中 film_clip 全表（含八词 + 粵語長片/粵語片/戲曲/銀幕/影星及经典演员补充词） |
| `film_related_core` | 仅命中 PIPELINE 八词：李小龍、任劍輝、芳艷芬、林鳳、吳楚帆、石堅、謝賢、粵劇 |
| `contemporary_only` | 上述四类内容 flag（parody/song/recitation/film）**全为 0**（可选列；与互斥版 contemporary 含义接近，但不排除与 `film_related_core` 的理论交叉——当前词表下 core ⊆ film_clip） |

命中关键词写入 `matched_*` 列（`|` 分隔）及汇总列 `matched_keywords`（`类别:词|词;...`）。

## 「电影口白」定义

**视频级条件 + 窗口级 singing 条件：**

- 该窗所属视频 `film_flag = 1`
- 且该窗 `singing_prob < 0.2`

窗口表列名：`dialogue_film`（仅当该窗已有 `singing_prob` 时取值 0/1；否则留空）。

无 `singing_prob` 时**不强行编造** `dialogue_film`。

## 输出文件

| 文件 | 说明 |
|---|---|
| `build_multilabel_flags.py` | 可复算脚本 |
| `video_multilabel_flags.csv` | 每视频一行：flags + matched keywords |
| `window_multilabel_flags.csv` | 每窗一行：继承视频 flags + `singing_prob`（若有）+ `dialogue_film` |
| `flag_counts_videos.csv` | 各 flag 视频数汇总（不做分层一致率） |
| `requirements.txt` | 依赖版本 |
| `_build_meta.json` | 本次运行元数据（覆盖率、来源路径） |

### `video_multilabel_flags.csv` 主要列

`video_id, title, upload_date, n_windows, speech_s, parody_flag, song_flag, recitation_flag, film_flag, film_related_core, contemporary_only, matched_parody, matched_song, matched_recitation, matched_film_clip, matched_film_related_core, matched_keywords`

### `window_multilabel_flags.csv` 主要列

`window_id, video_id, tier, idx, start, end, dur,`（视频 flags）`, matched_keywords, singing_prob, dialogue_film`

## 本次 flag 视频计数（567 视频）

| flag | n_videos | share |
|---|---:|---:|
| parody_flag | 7 | 1.23% |
| song_flag | 12 | 2.12% |
| recitation_flag | 15 | 2.65% |
| film_flag | 131 | 23.10% |
| film_related_core | 119 | 20.99% |
| contemporary_only | 408 | 71.96% |
| multi_content_flag_ge2（四类中 ≥2） | 6 | 1.06% |

窗口：4911；其中有 `singing_prob` 的约 51 窗（任务2试跑+冒烟局部）；`dialogue_film=1` 仅在这部分可算窗上出现。

## 待任务2合并项

1. 全量 `window_quality.csv`（或等价含 `window_id`/`uid` + `singing_prob`）交付后，重新运行本脚本左连接，刷新 `window_multilabel_flags.csv` 的 `singing_prob` / `dialogue_film`。
2. 任务2审过后再做任务3分层检验与一致率对比（**不在本目录本次范围**）。
3. 若任务2列名或路径变更，更新 `build_multilabel_flags.py` 中 `SINGING_PROB_CANDIDATES`。

## 复算

```bash
source /workspace/cantoai/.venv/bin/activate   # 或按 requirements.txt 建环境
python /workspace/cantoai/analysis/task3_multilabel_flags/build_multilabel_flags.py
```

仅读写分析目录与只读 SQLite；不碰音频。
