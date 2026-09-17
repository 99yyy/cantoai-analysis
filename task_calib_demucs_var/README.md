# task_calib_demucs_var

在 4911 个真实 window FLAC 上，用 **htdemucs** 分离后计算音乐床主指标 **`var_db`**（vocals/rest RMS 比，单位 dB）。

## 结论（一.1 全量）

| 项 | 值 |
|----|-----|
| CSV 行数 | **4911**（`window_var_db.csv`） |
| `demucs_ok` | **4911 成功 / 0 失败** |
| 全量墙钟 | **16172 s ≈ 4.49 h**（CST 2026-09-17 18:08→22:38） |
| 试跑 20 | **65 s**，外推 `est_hours≈4.43`（≤12 → 继续全量） |
| 权重 | **80.13 MB**（84025440 B，HF `955717e8.safetensors`），**未触 >2GB** |
| `var_db` 均值 | **17.98 dB**；中位 **12.72**；p25/p75 **7.14 / 25.06**；p10/p90 **4.78 / 42.81** |

输出目录：`/workspace/cantoai/analysis/task_calib_demucs_var/`

## 本地补丁：Separator 单例

上游脚本在每个 window 内 `Separator(model="htdemucs", device="cpu")`，全量会极慢。

**本目录已打补丁**：模块级 `get_separator()` 只建一次 Separator，`process_window` 全程复用。README 与脚本 docstring 均注明「本地补丁：Separator 单例」。

## 命令

```bash
cd analysis/task_calib_demucs_var
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu
# 注：本机 Python 3.13 无 numpy<2 的 wheel，实际安装为 numpy 2.2.x；requirements.txt 仍保留仓库约束。

# 试跑 20
.venv/bin/python scripts/run_demucs_var_db.py \
  /workspace/cantoai/corpus/dataset_v2/work/windows \
  -o artifacts/trial_20.csv --limit 20

# 全量
.venv/bin/python scripts/run_demucs_var_db.py \
  /workspace/cantoai/corpus/dataset_v2/work/windows \
  -o window_var_db.csv
# 日志：artifacts/full_run.log
```

## 输出 CSV

| 列 | 说明 |
|----|------|
| `window_id` | 文件名（无扩展名） |
| `rms_vocals` / `rms_rest` | 人声 / 伴奏（drums+bass+other）RMS |
| `var_db` | `20 * log10(rms_vocals / rms_rest)` |
| `demucs_ok` | 1=成功，0=失败 |
| `error` | 失败信息或 `rest_rms_zero` / `vocals_rms_zero` |

## 权重与约束

- 模型：htdemucs（Hybrid Transformer Demucs），`device="cpu"`
- 缓存路径：`~/.cache/huggingface/hub/models--adefossez--HTDemucs/`
- 单文件 **80.13 MB**（预期量级 ~80–316 MB），合计 **未超过 2GB**
- 只读音频；未改 sqlite / work 音频；未把权重/音频/`.venv` 提交 git
- 连续运行约 4.5 h（硬上限 12 h，未触发）

## 反对解释（勿过度解读 var_db）

1. **Demucs 人声泄漏**：音乐床中的弦乐/合唱/混响常被部分分入 `vocals`，抬高 `rms_vocals`，使 `var_db` 偏大，并不等于「说话声主导」。
2. **短窗分离不稳**：语料窗多为数秒级；htdemucs 在短片段上相位/瞬态估计不稳，同一视频相邻窗 `var_db` 可跳动十余 dB。
3. **rest 定义依赖四轨加和**：`rest = drums+bass+other`，非真实「非人声」；环境噪声、对白混响落入 `other` 时会压低 `var_db`。
4. **与 Brouhaha snr_db 不可互换**：Brouhaha 训练几乎剔除音乐噪声（论文 §4.1），其 snr_db 在音乐床场景不可靠；本任务以 `var_db` 为主、snr 仅参考。

## 产物

- `window_var_db.csv` — 全量 4911 行
- `trial_20_timing.json` / `full_timing.json`
- `artifacts/trial_20.csv`、`artifacts/trial_20.log`、`artifacts/full_run.log`、`artifacts/full_stats.json`
- `scripts/run_demucs_var_db.py`、`requirements.txt`

## 参考

- [Demucs (Meta)](https://github.com/facebookresearch/demucs)
- [Brouhaha (arXiv:2210.13248)](https://arxiv.org/abs/2210.13248)
