# task_calib_demucs_var

Compute **音乐床强度主指标** `var_db`（vocals/rest RMS ratio in dB）for window FLAC files using **htdemucs** source separation.

## 用法

```bash
cd task_calib_demucs_var

# 安装依赖
pip install -r requirements.txt

# 处理所有窗口 FLAC
python scripts/run_demucs_var_db.py /path/to/windows -o results.csv

# 限制处理数量
python scripts/run_demucs_var_db.py /path/to/windows -o results.csv --limit 100

# 干跑模式：用合成音频自测管道（不需要真实 FLAC）
python scripts/run_demucs_var_db.py --dry-run-synth -o _sample_out/window_var_db_sample.csv

# 从文件读取 window ID 列表
python scripts/run_demucs_var_db.py /path/to/windows -o results.csv --id-file window_ids.txt

# 从 stdin 读取 window ID
cat window_ids.txt | python scripts/run_demucs_var_db.py /path/to/windows -o results.csv --id-file -
```

## 输出 CSV 格式

| 列名 | 说明 |
|------|------|
| `window_id` | 窗口文件名（不含扩展名） |
| `rms_vocals` | 人声轨 RMS（科学计数法） |
| `rms_rest` | 伴奏轨 RMS（drums + bass + other 求和后的 RMS） |
| `var_db` | 人声/伴奏比（dB），主指标 |
| `demucs_ok` | 分离是否成功（1=成功，0=失败） |
| `error` | 错误信息（成功时为空，或特殊标记如 `rest_rms_zero`） |

## var_db 公式

```
var_db = 20 * log10(rms_vocals / rms_rest)
```

其中：
- `rms_vocals = sqrt(mean(vocals²))`
- `rms_rest = sqrt(mean((drums + bass + other)²))`
- 若 `rms_rest = 0`（纯人声），`var_db = +999.0`，标记 `error = rest_rms_zero`
- 若 `rms_vocals = 0`（纯伴奏），`var_db = -999.0`，标记 `error = vocals_rms_zero`

## 模型说明

使用 **htdemucs**（Hybrid Transformer Demucs），Meta 开源的音频源分离模型：
- 分离为 4 轨：`vocals`, `drums`, `bass`, `other`
- 模型权重约 316 MB，首次运行时自动下载
- 本脚本强制使用 **CPU**（`device="cpu"`），适合长时间批处理

## 为何使用 var_db 而非 Brouhaha snr_db

**Brouhaha** 是针对语音增强任务训练的 SNR 估计模型，其 `snr_db` 输出在**音乐床**场景下**不可靠**。

根据 Brouhaha 论文 **§4.1 Datasets**（arXiv:2210.13248）：

> We used noise segments from AudioSet and **discarded human vocalizations**. We also **downsampled music segments from 38% to 5%**, leading to a total of 1500 hours of noise segments.

关键问题：
1. **训练噪声几乎不含音乐**：Brouhaha 的噪声集主动将音乐占比从 38% 降至 5%
2. **人声被排除在噪声外**：训练时人声属于"信号"而非"噪声"
3. **音乐床被误判为信号**：当输入含强音乐床时，模型会将音乐当成信号的一部分，导致 SNR 高估

因此，本任务以 **htdemucs 分离后的 `var_db`** 为主指标，**Brouhaha `snr_db` 仅供参考**。

## 约束

- **CPU only**：脚本强制 `device="cpu"`，无需 GPU
- **运行时间**：全量 4,911 窗口预计数小时到十几小时
- **模型权重**：htdemucs 单文件约 316 MB，自动下载；若超过 2 GB 会退出
- 不修改 sqlite、不删除音频、不联网下载语料

## 自测

```bash
# 确认 --help 退出 0
python scripts/run_demucs_var_db.py --help

# 用合成音频跑通管道
python scripts/run_demucs_var_db.py --dry-run-synth -o _sample_out/window_var_db_sample.csv

# 检查输出
cat _sample_out/window_var_db_sample.csv
```

## 参考

- [Demucs (Meta)](https://github.com/facebookresearch/demucs)
- [Brouhaha paper (arXiv:2210.13248)](https://arxiv.org/abs/2210.13248)
