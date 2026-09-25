# TASK-12 开放分析

总体是这个频道的 567 条视频。聚类停在 `video_id`。
比较的是一致率：左侧读音与 `jp_realized` 经 trim 与 Unicode casefold 后整串相等。
声学标签 `jp_realized` 来自词典侧，一致率可能被高估。
`review_prior` 没有用来分层、过滤或加权。分子没有用 `jp_match`。

## 头条

只点名 `gap_tj_default_pm`、`gap_py_default_pm`、`gap_g2pw_default_pm`。
每个 gap 单独相对 0 判断。不跨工具比较 gap 大小。

一句话：在主评测集上，gap_tj_default_pm 点估计 121.779859，95% 区间 [108.726290, 134.698233]，结论 gap_above_0；gap_py_default_pm 点估计 -92.450095，95% 区间 [-109.187839, -74.634631]，结论 gap_below_0；gap_g2pw_default_pm 点估计 -52.079848，95% 区间 [-68.295167, -36.079606]，结论 gap_below_0。

## 四个一致率与三个 gap

- `agree_tj_pm` = 544.775287164046
- `agree_py_pm` = 330.54533288725327
- `agree_g2pw_pm` = 370.9155793464927
- `agree_default_pm` = 422.9954276792684
- `gap_tj_default_pm` = 121.77985948477752
- `gap_py_default_pm` = -92.45009479201516
- `gap_g2pw_default_pm` = -52.07984833277573

## Q1 Q2 Q3

Q1 不适用：主结果不是按序数切分的组间差，主集由文字工具两两相等性定义。
Q2 不适用：主结果是同一子集上的一致率与配对差，不是两组行加权组间差。
Q3 不适用：不是份额分解。gap 是定义差，不写「解释了」。

## Q4 区间

`master_seed` = 20260920。层 `h` = `main`。层种子 `int(sha256("20260920:main").hexdigest()[:8], 16)` = 2410426915。只有这一层。
`B` = 2000。`G` = 549。`ci_unreliable` = 0。
resample video_id with replacement; a cluster drawn k times contributes its main-set rows k times; recompute the global gap。
区间端点不进 `numbers`。
- `gap_tj_default_ci` 点估计 gap 121.77985948477752，对应 agree 544.775287164046，基线 agree_default 422.9954276792684，区间 [108.72629046619275, 134.69823322685747]。相对幅度点估计 0.28789876087529664，相对幅度区间 [0.2529020382484335, 0.3250724212387328]，不可比轮数 0。符号翻转 False。结论翻转 False。
- `gap_py_default_ci` 点估计 gap -92.45009479201516，对应 agree 330.54533288725327，基线 agree_default 422.9954276792684，区间 [-109.18783875306192, -74.6346313375299]。相对幅度点估计 -0.21856050619562353，相对幅度区间 [-0.25295766536599124, -0.1814620021974534]，不可比轮数 0。符号翻转 False。结论翻转 False。
- `gap_g2pw_default_ci` 点估计 gap -52.07984833277573，对应 agree 370.9155793464927，基线 agree_default 422.9954276792684，区间 [-68.29516723387533, -36.079606180346154]。相对幅度点估计 -0.12312153967835487，相对幅度区间 [-0.15790789563540972, -0.08634683637121843]，不可比轮数 0。符号翻转 False。结论翻转 False。
相对幅度每轮用该轮重算的 gap 除以该轮重算的 agree_default；分母为 0 的轮标不可比，不进入相对幅度区间。

## Q5

漏掉本应不同却被标成相同的行，主集会偏向更容易见到文字侧差异的子集，gap 的绝对值可能偏大。把噪声差纳入主集，gap 会被稀释。
两侧规模：`n_multi_disagree` = 8967，`n_tools_agree` = 130395。

## Q7

主集两两分歧模式：
- tj_ne_py=0,tj_ne_g2pw=1,py_ne_g2pw=1: 3135
- tj_ne_py=1,tj_ne_g2pw=0,py_ne_g2pw=1: 3464
- tj_ne_py=1,tj_ne_g2pw=1,py_ne_g2pw=0: 1725
- tj_ne_py=1,tj_ne_g2pw=1,py_ne_g2pw=1: 643
对照侧两两分歧模式（应全为 0 对不等）：
- tj_ne_py=0,tj_ne_g2pw=0,py_ne_g2pw=0: 130395
主集 `char` 顶频：
- 呢: 749
- 會: 525
- 話: 348
- 到: 301
- 下: 216
- 為: 201
- 上: 184
- 噶: 183
- 名: 173
- 咪: 168
- 啦: 154
- 嚟: 138
- 聽: 136
- 長: 127
- 揾: 125
对照侧 `char` 顶频：
- 嘅: 2509
- 係: 2199
- 人: 1707
- 有: 1536
- 一: 1530
- 個: 1348
- 唔: 1289
- 你: 1287
- 我: 1200
- 就: 1119
- 佢: 976
- 得: 974
- 都: 956
- 同: 951
- 好: 908
框内依赖列 distinct：
- char: distinct=3282
- tj: distinct=1537
- py: distinct=1487
- g2pw: distinct=1460
- default: distinct=1373
- realized: distinct=3033
「呢」在发布集可判定行上 750 行：next 为空 28，句末标点 0，非句末 722。判定只用 `next_char`。
非句末「呢」一致率（descriptive=1）：
- agree_tj_pm = 362.8808864265928
- agree_py_pm = 432.13296398891964
- agree_g2pw_pm = 87.25761772853186
- agree_default_pm = 441.82825484764544
pred 覆盖：主集 missing 0，对照侧 missing 0。缺行会在写结果前退出非零。

## 契约第 24 条计数

分子是左侧与 `jp_realized` 整串相等，不是 `jp_match`。
{
  "published": {
    "n_total": 164693,
    "n_empty_realized": 2183,
    "n_dur_le_0": 23860,
    "n_empty_and_dur_le_0": 712,
    "n_judgeable": 139362,
    "n_match_tj": 112519,
    "n_match_py": 110598,
    "n_match_g2pw": 110960,
    "n_match_default": 109750
  },
  "main": {
    "n_total": 8967,
    "n_empty_realized": 0,
    "n_dur_le_0": 0,
    "n_empty_and_dur_le_0": 0,
    "n_judgeable": 8967,
    "n_match_tj": 4885,
    "n_match_py": 2964,
    "n_match_g2pw": 3326,
    "n_match_default": 3793
  }
}

## 描述性：词典侧 ctx 与 default 不同的子集

descriptive=1。发布集 ∩ 可判定 ∩（规范化后 `jp_ctx` ≠ `jp_default`）。不进头条。
行数 6022。
- agree_tj_pm = 620.0597808037197
- agree_py_pm = 519.7608767851212
- agree_g2pw_pm = 512.6203918963799
- agree_default_pm = 160.24576552640318

## 逐字分歧表

descriptive=1。主集上按 `char` 汇总三工具两两不等次数。全表在 `manifest.json` 的 `char_disagreement`。
行数最多的 20 个字：
- 呢: n=749 tj≠py=473 tj≠g2pw=345 py≠g2pw=730
- 會: n=525 tj≠py=498 tj≠g2pw=118 py≠g2pw=505
- 話: n=348 tj≠py=38 tj≠g2pw=345 py≠g2pw=313
- 到: n=301 tj≠py=133 tj≠g2pw=185 py≠g2pw=284
- 下: n=216 tj≠py=68 tj≠g2pw=150 py≠g2pw=215
- 為: n=201 tj≠py=113 tj≠g2pw=117 py≠g2pw=173
- 上: n=184 tj≠py=110 tj≠g2pw=102 py≠g2pw=156
- 噶: n=183 tj≠py=183 tj≠g2pw=3 py≠g2pw=183
- 名: n=173 tj≠py=163 tj≠g2pw=123 py≠g2pw=60
- 咪: n=168 tj≠py=165 tj≠g2pw=85 py≠g2pw=161
- 啦: n=154 tj≠py=2 tj≠g2pw=154 py≠g2pw=152
- 嚟: n=138 tj≠py=27 tj≠g2pw=120 py≠g2pw=129
- 聽: n=136 tj≠py=130 tj≠g2pw=36 py≠g2pw=135
- 長: n=127 tj≠py=124 tj≠g2pw=18 py≠g2pw=126
- 揾: n=125 tj≠py=108 tj≠g2pw=125 py≠g2pw=17
- 當: n=124 tj≠py=110 tj≠g2pw=90 py≠g2pw=50
- 間: n=121 tj≠py=116 tj≠g2pw=17 py≠g2pw=119
- 咁: n=120 tj≠py=120 tj≠g2pw=120 py≠g2pw=0
- 生: n=120 tj≠py=99 tj≠g2pw=101 py≠g2pw=40
- 思: n=109 tj≠py=109 tj≠g2pw=0 py≠g2pw=109

