# 仓库布局（LAYOUT）

目的：多个 Cloud Agent 并发写入时，仓库不乱。原则只有一条——**每个目录只属于一种写入者，写入范围由 CI 的 scope-check 按 `rounds/ROUND-N.yaml: write_scopes` 机械执行，不靠自觉。** 一个 agent 多写了一个文件，不是整洁问题，是 CI 红。

## 目录与写入者

| 路径 | 内容 | 谁能写 | 怎么进 main |
|------|------|--------|-------------|
| `LOOP.md` `LAYOUT.md` `RESEARCH_LOG.md` `backlog.md` `REPORT.md` `README.md` | 回路规则、布局、研究日志、待办、报告 | fyp / Tom | `chore/` 分支 PR |
| `.cursor/` `.github/` | 契约、hooks、Bugbot、CI | Tom | 直接由 Tom 经 PR |
| `data/corpus_v2.sqlite` | 钉死的语料（sha256 记在 `frame.yaml: inputs`） | 一次性提交后不再改 | — |
| `fixtures/` | `schema.sqlite`、`manifest.schema.json`、`schemas/*.json` | Tom（`schema:` PR） | `schema:` PR |
| `frame.yaml` `sql/` `src/` | 抽样框、全部 SQL、分析库。**src 与轮次无关**：轮次只出现在 `rounds/` 和输出目录名里，不出现在 src 文件名里 | `impl` scope | `cursor/rN-impl-` |
| `tests/` | 断言反例、`mutations/`、空值传播测试 | `tests` scope | `cursor/rN-tests-` |
| `scripts/` | 只放 CI 检查器：`contract_check` `scope_check` `sql_explain` `audit` | Tom / `chore/` | `chore/` PR |
| `rounds/ROUND-N.md` `rounds/ROUND-N.yaml` | 一轮的声明 | fyp | `chore/` 分支 PR |
| `ROUND-N/<comparison_id>/` | **固定五件**：`metrics/*.json` `manifest.json` `STATUS.json` `checks.json` `README.md`。多一个文件即越界 | 该 comparison 的 agent | `cursor/rN-<comparison_id>-` |
| `ROUND-N/audio/` | 音频推断产出 | 音频员 | `box/rN-audio-` |
| `review/ROUND-N/method/<mandate>.md` | 方法审，**每个审稿 agent 只准写这一个文件** | `mr_falsify` `mr_tools` `mr_stats` | `cursor/rN-mr_<mandate>-` |
| `review/ROUND-N/audit.md` | 行为审计：这一轮**怎么做的**，六个固定问题各带 commit sha | `audit` scope | `cursor/rN-audit-` |
| `review/ROUND-N/result.md` `review/ROUND-N/recompute/` | 独立重算的结论与其一次性代码。`recompute/` 是隔离区：不 import `src/`，也没有任何东西 import 它 | `review` scope | `cursor/rN-review-` |
| `task*/` 与根目录的 CSV/PNG | 回路之前的产物，**冻结**：只读输入，不再新增 `task_*` 目录，不再往根目录写结果 | 无人 | — |

## 三条硬规则

1. **轮次号只在路径里，不在代码里。** `src/round3.py` 是过渡产物；后续 impl 任务把它改成由 `rounds/ROUND-N.yaml` 驱动的通用 runner，之后 src 里不得出现 `roundN` 命名的模块。同一份代码跑所有轮，轮与轮的差别全在 yaml。
2. **审稿 agent 不产出脚本。** 方法审的三个 agent 各写一个 markdown；重算 agent 的代码只能落在 `review/ROUND-N/recompute/`，且永远不会被 import。想把审稿里的检查变成长期规则，唯一的路是：写进 backlog，由下一轮的 `tests` scope 做成反例、或由 Tom 加进 `scripts/contract_check.py`。
3. **栅与它度量的东西不得同时改。** 期望值、容差、阈值、变异补丁、反例模式、contract_check 的检查条数，这些是「栅」。移动栅的 PR 不得同时改 `src/` `sql/` `data/` `scripts/`，且正文必须有一行 `BAR-CHANGE: <理由>`；为新代码新增栅不算。由 CI 的 `history-audit` 执行。
4. **输出目录的文件集合是封闭的。** `write_scopes` 里列的是精确的文件名，不是 `**`。agent 想多写一个中间文件，就在自己的 VM 里写，不进仓库。

## 分支前缀

- `cursor/r<N>-<scope_id>-…`：Cloud Agent，受 scope-check 约束。
- `box/r<N>-<scope_id>-…`：共享机器上的 bot，受同样约束。
- `chore/…`：fyp 的声明与文档。只能改 `rounds/`、`RESEARCH_LOG.md`、`backlog.md`、顶层文档、`STOP`、`ROUND-*/STATUS.json`；碰 `expected/`、`src/`、`tests/`、`scripts/` 一律红。
- `repair/…` 或 `cursor/repair-…`：Tom 指定的工具修复。免 scope 检查，但前缀本身让它在 git 历史里一眼可辨。
- 其他前缀一律红，不再静默放行。

## 一轮结束时的状态

`rounds/ROUND-N.*` 一份声明，`ROUND-N/` 下每个 comparison 五件产物，`review/ROUND-N/` 下三份方法审、一份结论、一份行为审计、一个隔离的重算目录，`RESEARCH_LOG.md` 追加一节。除此之外这一轮不在仓库任何别的地方留下文件。
