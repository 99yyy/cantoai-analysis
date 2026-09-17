# ROUND-1 阶段1 · 方法审（复审）

- 输入：`rounds/ROUND-1.md`（打回后修订版；计数 1/2）
- 判定：**通过**
- 对照：`review/ROUND-1/method.md` 首版硬条件 1–6

## 硬条件逐条复核

| # | 条件 | 复核 | 结果 |
|---|------|------|------|
| 1 | 钉死 `window_quality_with_flags.csv` | 判据与契约均强制该路径；本机 `head -1` 确认含 `flag_sing`，无 flag 的 `window_quality.csv` 不含 | 满足 |
| 2 | 统一产物路径 | 判据/契约/预测均用 `analysis/ROUND-1/` + `metrics/corr_summary.json` 与 `flag_sing_contrast.json`；无矛盾 `artifacts/` | 满足 |
| 3 | 可重跑命令产出全部判据 | 给出 limit 推理 + `--summarize` 两步；冒烟要求双 JSON 键齐全 + `STATUS.json`/`smoke_ok` | 满足 |
| 4 | 配对定义 | 写明 `clap_ok=1` ∩ 内连接 `singing_prob`；`n_paired` 等于该行数 | 满足 |
| 5 | 小样本门槛 | 全量前必须 `--limit 20`（或 fixtures）写出双 JSON 且 `smoke_ok: true` | 满足 |
| 6 | 预测 commit 可核验 | 已写明仓库 `https://github.com/99yyy/cantoai-analysis` 与 `rev-parse` 命令；工作区 git 无此对象（预期，非分析库） | **文档满足**；执行 launch 前 fyp 须在分析库 clone 上跑通 `rev-parse` 并将输出记入 ROUND「验证记录」 |

## advisory（不阻塞）

- `flag_sing=1` 约 14 窗，H2 检验力低；保持现有声明即可。
- 英文 singing/speaking 提示对粤语戏曲/口白可能偏；留给一.3。
- 本复审未能在无凭证环境下 `git ls-remote` 核验 `03a05f78…`；**合并/launch 前由 fyp 补一行验证记录**即可，不作为第二次打回。

## 结论

**通过。** 可以进入阶段2（Cloud Agent launch 写 `scripts/`）。launch 前请 fyp 在 `cantoai-analysis` clone 确认预测 commit 存在并写回 ROUND 验证记录。
