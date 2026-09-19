# backlog

按顺序取题。状态：`待办` / `进行中` / `完成` / `需 Tom 决定` / `跳过`。

| 序 | 条目 | 状态 | 备注 |
|----|------|------|------|
| 1 | 一.1 htdemucs 全量 `var_db` | 完成 | `task_calib_demucs_var/`；`review/calib-1.1-result.md` |
| 2 | 一.2 CLAP `clap_sing` 与 PANNs 对照 | 完成 | **ROUND-1** 结轮；ρ≈0.40 → 一.3 须双轨；`analysis/ROUND-1/` @ `4eab466` |
| 3 | 一.3 人工听辨样本 200 窗抽样与 `listening_sheet` | 进行中 | **ROUND-2**；审批点：样本就绪通知 Tom |
| 4 | 二 SenseVoice-small-Yue 全量重转写；Qwen3-ASR-1.7B 先 20 窗估时 | 待办 | 超 2GB 权重或 >12h 估时先升级 |
| 5 | 三 三方逐字投票实验（Flash / SenseVoice / Qwen3） | 待办 | ROVER 风格；在转写一致字上重测 |
| 6 | CTC 音节对齐 | 需 Tom 决定 | 可能需 GPU |
| 7 | 基频声调核查 | 需 Tom 决定 | 可能需 GPU |

完成后在本表改状态，并在 `RESEARCH_LOG.md` 留一句指针。

| 9 | BOILER 列表补片尾句 + 重建发布集 | 待办 | `06_normalise_text.py`；单开一轮；勿夹审计 PR |
| 10 | `review_prior`：`jp_match=none` 勿与完全一致同归 low | 待办 | 单开一轮；勿夹审计 PR |

## TASK-6 收口

- 审计：`review/TASK-6/audit.md` @ `6530f02` — **FINDINGS: 4**（worker 写了根目录 `pytest.ini`；开放结论把剩余差距归因到 tone/segment 过强；film/other 四格缺 contract-24 六计数进 manifest；`src/` 有 SQL 字符串字面量）。结论只记在此，不直接变成下一题。
- keep rate：产出 39 个数字，留下 39 个（`output-check` 39/39 agree）→ **39/39**。

## TASK-7 收口

- 审计：`review/TASK-7/audit.md` — `verdict: supported`（`gap_other_common_pp` 7.3304；worker 整簇 bootstrap 95% CI 不含 0）。结论只记在此，不直接变成下一题。
- keep rate：产出 10 个数字，留下 10 个（`output-check` 10/10 agree）→ **10/10**。
- 任务书仍 `status: open`：`cursor[bot]` 不能改 brief（agent `no_brief`），也不能开 `chore/`（actor 不在 owner allowlist）。需要 owner 用 `chore/` 盖 `status: closed` 与 `corpus_sha:`。

## LOOP 预算（启动次数，不是美元）

一轮家族（父任务 + `-b` + `-c`）共享 **16** 次 Cloud Agent 启动。碰到上限是 `subtype: out_of_budget`，停下来报告 Tom。账本是 `tasks/TASK-N/launches.json`，由 coordinator / auditor 追加。同一语料 pin 上关了几道题只在本 backlog 记一笔，不进 RESULT，也不叫 `val_iterations`。
