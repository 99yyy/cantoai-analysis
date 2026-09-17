# SCHEMA.md — iCantonese / CantoAI analysis contracts

Cloud Agent 只应使用本仓库内的 `fixtures/sample.sqlite`、本文件，以及已提交的 CSV（如 `task3_multilabel_flags/`、`task2_window_quality/window_quality.csv` 的样例切片）。**禁止**假设可访问真实全库、音频、模型权重或外网下载数据。

## 一致率口径（agreement）

- 判定字段：`syllables.jp_match` ∈ {`exact_default`, `exact_alt`, `tone`, `segment`, `diff`, `none`}
- **一致** = `jp_match ∈ {exact_default, exact_alt}`
- 默认分析层：**tier A+B**（`windows.tier` / `syllables.tier` 为 `A` 或 `B`）
- **音节加权一致率** = 一致音节数 / 音节数
- **视频中位数一致率** = 先按视频算该视频音节一致率，再对视频取中位数
- **Bootstrap 95% CI**：按**视频**重采样（有放回），B≥2000；对每次重采样重算上述两种口径

这是模型（声学 Jyutping）与词典（ToJyutping）的一致性，**不是**人工听辨准确率。

## 表：`videos`

| 列 | 含义 |
|---|---|
| video_id | YouTube 视频 id（主键） |
| title | 标题 |
| upload_date | 上传日（常见 YYYYMMDD 整数/文本） |
| 其他元数据列 | 以 `PRAGMA table_info(videos)` / sample.sqlite 为准 |

## 表：`windows`

每个切分段（窗口）。常见列：

| 列 | 含义 |
|---|---|
| window_id / uid | 窗口 id，通常 `{video_id}_{idx:03d}` |
| video_id | 所属视频 |
| tier | `A` / `B` / `C`（导出与主分析用 A+B） |
| 时长/语速相关列 | 用于字/秒分箱；以 sample 为准 |
| flag_sing | 库内歌唱标记（极少；勿与 singing_prob 混用） |

## 表：`syllables`

| 列 | 含义 |
|---|---|
| video_id / window_id | 归属 |
| tier | A/B/C |
| jp_ctx / jp_default 等 | 词典 Jyutping（ToJyutping） |
| jp_realized | 声学模型 Jyutping（wav2vec2bert-jyutping） |
| jp_match | 六种判定之一（见上） |
| 声母/韵尾/声调相关列 | 若库中已拆好则直接用；否则从词典读音解析 |

具体列名以 `fixtures/sample.sqlite` 的 schema 为准；脚本应对缺失列给出清晰错误。

## 多标签（任务3）

来自 `task3_multilabel_flags/video_multilabel_flags.csv`（可并存，非互斥）：

- `film_flag`, `song_flag`, `parody_flag`, `recitation_flag`
- `contemporary_only`：四类 flag 皆假时的当代口播代理
- **电影口白**（窗口级）= 该视频 `film_flag=1` **且** 该窗口 `singing_prob < 0.2`

## 窗口质量列

来自 `task2_window_quality/window_quality.csv`：

| 列 | 含义 |
|---|---|
| window_id | 与 windows 对齐 |
| music_prob | PANNs 音乐概率 |
| singing_prob | PANNs 歌唱概率 |
| snr_db | Brouhaha 估计 SNR |
| dnsmos_ovrl | DNSMOS OVRL |

样例切片：`fixtures/sample_window_quality.csv`（与 sample.sqlite 同一批视频）。

## fixtures/sample.sqlite

- 含 **5** 个视频的 `videos` / `windows` / `syllables` 切片
- 至少 1 个 `film_flag=1` 与 1 个 `contemporary_only=1`
- Cloud Agent 自测应只在此库 + fixtures CSV 上跑通

## 禁止事项

- 不改真实 `corpus.sqlite`、不删文件、不联网下载语料/权重
- 不写分析结论进 PR（只写可运行脚本、测试与最小 README 用法）
- 不提交音频、全库 sqlite、模型权重、`.venv`

## sample.sqlite 实测列名

### videos

`video_id`, `title`, `upload_date`, `n_windows`, `speech_s`

### windows

`uid`, `video_id`, `idx`, `start`, `end`, `dur`, `start_sample`, `end_sample`, `boundary_start`, `boundary_end`, `lang`, `text_raw`, `text_norm`, `text_clean`, `flag_hai`, `flag_simp`, `flag_sing`, `flag_boiler`, `chars_per_sec`, `aligned`, `coverage`, `first_s`, `in_range`, `max_zero_run`, `tone_shift_suspect`, `n_syllables`, `tier`, `text_human`

### syllables

`syl_id`, `uid`, `video_id`, `pos`, `c0`, `char`, `start`, `end`, `dur`, `win_start`, `jp_default`, `jp_ctx`, `jp_candidates`, `n_cand`, `prev_char`, `next_char`, `ctx`, `tier`, `jp_realized`, `jp_match`, `review_prior`, `verification_status`, `verification_note`
