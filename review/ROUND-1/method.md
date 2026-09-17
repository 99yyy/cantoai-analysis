# ROUND-1 阶段1 · 方法审

- 输入：`rounds/ROUND-1.md`
- 判定：**改**（未通过；满足下列硬条件后再送审）
- 方法审打回计数建议记入 ROUND：`1/2`

## 审阅要点

| 项 | 现状 | 结论 |
|----|------|------|
| 预测是否写死 | 有 H1/H2/H3 与量化阈值；但所写预测 commit `03a05f78…` **在工作区 `/workspace/cantoai` 无法 `git cat-file`** | 硬条件：在 ROUND 写明仓库（`cantoai-analysis` vs 工作区）且该 commit 可取到 |
| 判据可否重算 | Spearman / Mann–Whitney / 中位数均可由 CSV+JSON 重算，但产物路径与输入表未钉死 | 硬条件如下 |
| 工具适用性 | LAION-CLAP 与 PANNs 均标明**未校准**；`flag_sing=1` 仅 **14** 窗 | 硬条件：全量前必须有小样本冒烟门槛 |
| 脚本契约 | 示例命令未产出 JSON 判据；`flag_sing` 来源写成「可选 sqlite 或 CSV」 | 硬条件如下 |

## 硬条件（可验证；须全部满足）

1. **钉死 `flag_sing` 输入路径**  
   ROUND「脚本契约」与 README 必须写明全量使用：  
   `analysis/task2_window_quality/window_quality_with_flags.csv`  
   （当前契约写的 `window_quality.csv` **无** `flag_sing` 列，H2 无法重算。）  
   验证：`head -1 analysis/task2_window_quality/window_quality_with_flags.csv` 含 `flag_sing`；`window_quality.csv` 不含。

2. **统一产物路径**  
   将「判据」与「脚本契约」中的 JSON 路径改成同一前缀，建议：  
   - `analysis/ROUND-1/window_clap_sing.csv`  
   - `analysis/ROUND-1/artifacts/corr_summary.json`  
   - `analysis/ROUND-1/artifacts/flag_sing_contrast.json`  
   验证：`rounds/ROUND-1.md` 内上述三路径各出现且不再出现互相矛盾的 `artifacts/corr_summary.json`（或契约与判据同改 `artifacts/`，二选一）。

3. **一条（或固定两条）可重跑命令须产出全部判据文件**  
   示例命令须包含：windows 目录、quality（含 flag）路径、输出 CSV、以及写出 `corr_summary.json` / `flag_sing_contrast.json` 的步骤（可第二命令，但路径写死）。  
   验证：按 ROUND 文档对 `--limit 20` 跑通后，下列文件存在且含键：  
   - `corr_summary.json` 含 `spearman_clap_vs_panns`, `n_paired`  
   - `flag_sing_contrast.json` 含 `median_clap_flag1`, `median_clap_flag0`, `n_flag1`, `n_flag0`（及 p 值或「n_flag1<10 时的 CI 字段」）

4. **配对定义写进契约**  
   Spearman 仅对 `clap_ok=1` 且能与 `singing_prob` 内连接的行；`n_paired` 等于该行数。  
   验证：独立 `pandas` 内连接行数 == `corr_summary.json["n_paired"]`。

5. **未校准工具的小样本门槛（适用性）**  
   全量 4911 前必须：`--limit 20`（或 fixtures）成功写出上述 JSON，且 README/ROUND 写明「小样本通过后才全量」。  
   验证：存在 `analysis/ROUND-1/artifacts/`（或文档指定目录）下 limit 冒烟产物，或 STATUS 记录 `smoke_ok: true`。

6. **预测 commit 可核验**  
   ROUND 元数据写清仓库 URL/名，且 `git -C <repo> rev-parse --verify 03a05f78…^{commit}` 退出码 0；方法审通过后不得改「预测」段（仅允许改契约路径类硬条件）。

## advisory（不计入硬条件）

- `flag_sing=1` 仅 14 窗，H2 检验力极低；保持 ROUND 已有声明即可，结果阶段勿把非显著解读为「不敏感」。
- 提示词仅英文 singing/speaking，对粤语戏曲/口白可能系统偏；一.3 再标定即可，本轮对照仍可做。
- 权重 >2GB 停跑规则已写，保留。

## 结论

**改。** 未满足前不建议 Cloud Agent launch / 全量执行。满足硬条件 1–6 后把 `rounds/ROUND-1.md` 阶段改为可再审，并 1:1 通知复审方法。
