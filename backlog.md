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

| 8 | 基础设施：`scripts/audit.py`（过程可审计） | 进行中 | 规格 `docs/AUDIT-SPEC.md`；非 ROUND；阶段2–4 |
| 9 | BOILER 列表补片尾句 + 重建发布集 | 待办 | `06_normalise_text.py`；单开一轮；勿夹审计 PR |
| 10 | `review_prior`：`jp_match=none` 勿与完全一致同归 low | 待办 | 单开一轮；勿夹审计 PR |
