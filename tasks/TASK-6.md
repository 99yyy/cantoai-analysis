# TASK-6：2025 年之后一致率下降，能被解释多少

## 目标

**发布集在 2025 年及之后的一致率明显低于之前。把这个差距分解开，说清其中多少能由语料里已有的列解释，剩下多少不能。**

不修任何东西，不试图把分数提高。要回答的只有一件事：原因在哪一层。

## 输入

只读 `data/corpus_v2.sqlite`。读之前先算它的 sha256 并与 `README.md` 比对，不符就退出非零。不跑任何模型，不碰音频，不改数据库。

## 定义（两条算路必须用同一套）

- **发布集**：`windows.tier IN ('A','B')`。
- **期间**：`post` 是 `substr(videos.upload_date,1,4) >= '2025'`，其余为 `pre`。
- **一致率**：按契约第 24 条，`n_match / n_judgeable`，其中 `n_match` 是 `jp_match IN ('exact_default','exact_alt')` 的音节数，`n_judgeable = n_total - n_empty_realized - n_dur_le_0`。四个计数都要出现在输出里。
- **旧片组**：视频标题包含以下任一者——`粵劇` `任劍輝` `芳艷芬` `李小龍` `林鳳` `吳楚帆` `石堅` `謝賢` `新馬師曾` `白雪仙`。其余为 `other`。这是标题代理，不是内容判断，结论里要这么说。
- **稀有字**：该字在**全库全部 tier** 出现少于 10 次。
- **pp** 是百分点，**pm** 是千分之一。

## 要交的数字

下面是这个任务必须交出的全部数字。**这里只有名字和容差，没有值**——值由 worker 和 verifier 各自从语料算出，两条算路必须在容差内一致。

```numbers
# name                     tol
n_videos_pre               0
n_videos_post              0
n_judgeable_pre            0
n_judgeable_post           0
gap_contract_pp            0.05
gap_all_pp                 0.05
gap_excl_none_pp           0.05
gap_excl_zerodur_pp        0.05
agree_film_pre             0.0005
agree_film_post            0.0005
agree_other_pre            0.0005
agree_other_post           0.0005
did_film_pp                0.05
rare_share_pre             0.0005
rare_share_post            0.0005
rate_tone_pre_pm           0.5
rate_tone_post_pm          0.5
rate_segment_pre_pm        0.5
rate_segment_post_pm       0.5
rate_diff_pre_pm           0.5
rate_diff_post_pm          0.5
rate_none_pre_pm           0.5
rate_none_post_pm          0.5
```

各自的算法：

- `gap_contract_pp` 是 `agreement(pre) - agreement(post)`，用契约第 24 条的分母。
- `gap_all_pp`、`gap_excl_none_pp`、`gap_excl_zerodur_pp` 是同一个差，分母分别换成：全部 A+B 音节；只排除 `jp_match='none'`；只排除 `dur<=0`。三者只用于稳健性对照。
- `agree_*` 四个是 film/other × pre/post 的四格一致率，契约分母。
- `did_film_pp = (agree_film_pre - agree_film_post) - (agree_other_pre - agree_other_post)`。
- `rare_share_*` 是稀有字音节占该期 A+B 音节的比例。
- `rate_<verdict>_<period>_pm` 是该期 A+B 中该 `jp_match` 取值的千分比，分母是该期 A+B 全部音节。

## 还要交的东西（这部分不进 numbers 块）

**一个分解**：期间差距里，多少由可观测变量的组成差异解释，剩下多少。用哪些变量、怎么标准化，由你决定，但必须声明选了什么、为什么、每个变量从哪来。剩余差距要带按 `video_id` 整簇 bootstrap 的区间。

**一条对剩余部分的具体假设**，写成「用什么数据、做什么比较、什么结果会否定它」。写不成这个形式的就不要提。

**一句话结论**。

这部分两条算路不会一致，也不要求一致——它由 Tom 和 `auditor` 判断，不由 `output-check` 判断。

## 已知的坑

`tier`、`coverage`、`chars_per_sec`、`aligned` 是被评估模型自己的产物（契约第 27 条）：用它们分层就要同时报未分层的那一版。

`dur > 0` 不得单独用作筛选条件（第 25 条）。`review_prior` 不得用来分层、过滤或加权（第 26 条）。

按年切分时每格的视频数要一并报出来：2021 和 2023 的样本很小，别把小格当趋势。

## 分工

- `worker`，分支 `cursor/t6-worker-…`：写 `src/`、`sql/`、`tests/`，交 `tasks/TASK-6/results.json` 与上面那部分开放分析。
- `verifier`，分支 `cursor/t6-verifier-…`：**不读 worker 的代码**，只读本文件和语料，用自己的 SQL 把 23 个数字重算一遍，交 `tasks/TASK-6/verify.json`。
- 有 `match:false` 就把不匹配的行发回 worker，最多两次；仍不匹配就停，两套数字一起升级给 Tom。
- 两个都合入后放 `auditor`，写 `review/TASK-6/audit.md`。

两个 agent 都不能改本文件——`tasks/` 在 `scope-check` 的拒绝清单里。
