# AUDIT-SPEC：过程可审计（`scripts/audit.py`）

**性质**：基础设施任务，**不是**研究 ROUND；不套 ROUND 模板。仍走阶段 2–4：Cloud Agent launch 写脚本 → 分析员 fixtures 冒烟 → 审稿员审 → fyp 合并。

**定位**：`audit.py` **替代**审稿员阶段 4 的手工重算（不是追加一步）。一条命令跑完全部检查；退出码非零则该轮不能收。

**ROUND-2 相关**：听辨 **不重切**；阶段 4 仍按含/不含 tier C（及 lang=yue / A+B）两套报（见 `rounds/ROUND-2.md`）。

---

## 实现约束

1. **只读**：绝不改动语料、数据库、发布 CSV、权重。
2. **依赖**：仅 **Python 标准库 + `sqlite3`**（不要 pandas/numpy）。
3. **独立性**：每条检查独立；一条失败不影响其余继续跑。
4. **输出**：一屏以内；每行格式：`PASS|FAIL <名称> <实测值>（期望：…）`（或等价清晰格式）。
5. **退出码**：任一 FAIL → 非零；全 PASS → 0。
6. **CLI**：`--round N`（至少支持 `2`；无 `--round` 时跑语料级检查 C/L/T）。
7. **路径**：从环境变量读取，**不写死绝对路径**：
   - `ICANTO_ROOT`：语料根（含 `corpus/dataset_v2` 或等价；库、脚本、STATS、info.json）
   - `ANALYSIS_ROOT`：分析仓库根（含 `ROUND-2/listening_sheet.csv`、`rounds/` 等）
8. **fixtures**：分析仓库内提供最小 sqlite/CSV/STATS 切片，使冒烟可在无全库时跑通结构；全库期望值以下表「2026-09-18 实测」为准（在真实 `corpus.sqlite` 上断言）。

---

## 分层自洽（C）

| ID | 断言 | 2026-09-18 实测 | 期望 |
|----|------|-----------------|------|
| **C1** | 用 `common.tier_of`（或语料内同等函数）重算 tier，与存储值不符行数 | 0（目前零校验） | == 0 PASS；脚本须真正调用重算，禁止空跑 |
| **C2** | `syllables.tier` 与所属 `windows.tier` 不一致 | 0 | == 0 |
| **C7** | tier C 必须可由下列五条之一解释：`lang≠yue` / `flag_sing` / `cps>8` / `coverage<0.2` / `in_range=0`；无法解释的行数；五条并集大小 | 无法解释 0；并集恰 472 | 无法解释 == 0；并集 == 472（或与当前库一致并打印实测） |

### 当前即为 FAIL（须如实报 FAIL，不要改期望来「洗绿」）

| ID | 断言 | 2026-09-18 实测 | 期望（规范） |
|----|------|-----------------|--------------|
| **C3** | tier A/B 中 `jp_realized` 为空或 `jp_match='none'` | **2183** | == 0 → **FAIL**。注：`09` 的 `review_prior` 把 `none` 判为 low，与「完全一致」同桶 |
| **C4** | tier A/B 中 `dur<=0` 的音节 | **23860**（发布集约 14.5%） | == 0 → **FAIL**。注：`12_review_sample` 用 `s.dur>0` 排除它们；CSV 三位小数另造约 79 个零宽 |
| **C5** | tier A/B 中 `coverage>1.2` | **29**（全库 `coverage>1` 为 856，最大 12.321） | == 0 → **FAIL**。注：coverage 是首末汉字跨度比非占用率；真实占用率下 573/3048 个 tier A &lt; 0.5 |
| **C6** | `windows.aligned` 不同取值个数 | 取值仅 `(1,)`，n=4911 | 取值数 **> 1** → **FAIL**。注：`09` 的 NO_ALIGN 与 `10_validate` 的 tier-A 对齐断言从未触发 |
| **C8** | 按 `09` 导出 SQL 重放，与 `syllables_AB.csv` 逐格比对 | **131** 行时间戳差 ±0.01；`runs` 仅 1 条无法判定 CSV 出自哪次 build | 差分为 0（或在容差政策写明）；须打印 runs 条数与差分计数 → 当前 **FAIL** |
| **C9** | README 称发布集在 `dataset_v2/`，实际路径 | 实际在 `dataset_v2/dataset_v2/` | 文档路径与真实目录一致 → **FAIL**（检测嵌套目录或 README 声明） |
| **C13** | `12_review_sample` 抽样框覆盖发布集比例；对外报数口径 | 覆盖 **57116/164693 = 34.7%**，对外按 164693 报 | 脚本输出覆盖率；若对外报数 ≠ 抽样框大小则 **FAIL** |

---

## 泄漏与内容（L，优先级最高）

| ID | 断言 | 2026-09-18 实测 | 期望 |
|----|------|-----------------|------|
| **L1** | 各视频 `info.json` 的 `channel_id` 去重数；按视频聚类的 CI 依赖频道数 | **569** 份 info 的 `channel_id` **全部相同**（`@icantonese`） | 显式输出 `n_channels`；若 `n_channels==1` 则 **FAIL**（或 WARN 政策写明，默认 FAIL） |
| **L2** | tier A 中同一 `text_clean` 出现次数 | `如果覺得內容啱睇嘅subscribe`：**512** 窗 / 512 视频，`flag_boiler=0`，其中 **410** 在 tier A（占 tier A 窗 13.5%、音节 4.0%）；BOILER 列表（`06_normalise_text.py:81`）仅 5 个台标串 | tier A 中任一 `text_clean` 出现次数 **≤ 2** → 当前 **FAIL** |
| **L3** | A+B 中完全重复的 `text_clean` | **1131** 行 / **121** 组（约 25.5% 发布窗） | 重复组数 == 0 或按政策阈值；默认报 FAIL 若组数&gt;0 并打印计数 |
| **L4** | 音节时间戳超出所属窗口；相邻窗重叠 | 超出 **96**（最极端 **9.44s**）；重叠 **254** 对 | 超出 == 0 且重叠 == 0 → **FAIL** |
| **L5** | `n_syllables=0` 且 `coverage=0` 的窗口 | **144**，全在 tier C 但仍计入总量 | 打印计数；若计入对外总量则 **FAIL**（或明确标记） |
| **L6** | VAD 窗口丢弃可追溯性 | VAD **5097** 窗，丢弃 **186** 仅布尔无原因；`ids.txt` **568** 视频，`YJ-WX_ES5Jc` 产出 0 窗后静默消失；`STATS.json` 对这两步无记录 | 丢弃须有原因字段/日志；消失视频须入 STATS → **FAIL** |

---

## 口径（T）

| ID | 断言 | 2026-09-18 实测 | 期望 |
|----|------|-----------------|------|
| **T1** | 三个时长并输出且标明口径 | `sum(windows.dur)=17.304h`（含 padding）；`sum(videos.speech_s)=16.357h`（STATS 头条）；A+B 实际 speech **15.170h**；对外写 16.36h 比实际高 **7.8%** | 同时输出三值+标签；若对外宣称时长 ≠ A+B 实际 speech 则 **FAIL** |
| **T3** | 不要重复 `10_validate` 中结构上不可能失败的断言 | 9 条里 5 条不可能失败 | audit **不**复制空跑断言；本项为元检查 PASS（文档约束） |
| **T4** | `STATS.json` 九项计数与当前库一致 | 完全一致 | == → PASS（回归基线） |

---

## `--round 2`（听辨样本）

路径：`$ANALYSIS_ROOT/ROUND-2/listening_sheet.csv`（及 `rounds/ROUND-2.md` 预测 commit 元数据）。

| ID | 断言 | 2026-09-18 实测 | 期望 |
|----|------|-----------------|------|
| **R1** | sheet 中 `tier` ∉ {A,B} 的行数（需 join sqlite） | **42**/200 | 打印；规范上发布框应为 0 → **FAIL**（已知偏差，仍报 FAIL） |
| **R2** | `lang ≠ yue` | **32** | 打印；期望 0 → **FAIL**（已知） |
| **R3** | `both_high` 层 40 行中 tier C 数；全库 `flag_sing=1` 窗数 | both_high 中 C **18**/40；全库 flag_sing=1 仅 **14** | 打印；both_high∩C 期望 0 → **FAIL** |
| **R4** | `human_label` ∈ 六值集合；列名顺序 = `SHEET_COLUMNS`；UTF-8 无 BOM；LF | 结构应满足 | 结构违规 → FAIL；否则 PASS |
| **R5** | ROUND-2 预测 commit 是结果 commit 的祖先（分析库 git） | 预测 `fffad051…` | `merge-base --is-ancestor` → PASS/FAIL |

`SHEET_COLUMNS` =  
`window_id,video_id,film_flag,clap_sing,singing_prob,var_db,stratum,human_label,annotator_note,forced_flag_sing`

合法 `human_label`：`dialogue|singing|recitation|mixed|transcription_error|unset`

---

## 验收

- fixtures 冒烟：无全库时也能跑通，对缺失输入打印 SKIP 或明确错误，不崩溃。
- 真实库：在 `ICANTO_ROOT` 指向 `/workspace/cantoai`（或文档约定布局）时，上述已知 FAIL 必须出现为 FAIL（不得改期望值抹平）。
- 一屏摘要 + 非零退出码当存在 FAIL。

---

## 不在本 PR（进 backlog，各自单开一轮）

1. `06_normalise_text.py` BOILER 列表补片尾句 → tier 会变、发布集需重建。  
2. `review_prior` 不得把 `jp_match='none'` 与完全一致同归 `low`。
