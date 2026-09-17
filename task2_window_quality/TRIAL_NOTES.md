# Task2 试跑笔记（50 窗）

## 结论摘要
- 试跑成功：50/50，三工具失败数均为 0。
- `est_hours = 1.567`（公式 `(t_50/50)*4911/3600`），**≤ 12**，可继续全量。
- 未触发 >2GB 模型停机规则。

## 数据清点
- FLAC：`/workspace/cantoai/corpus/dataset_v2/work/windows/*.flac` → **4911**，命名 `{video_id}_{idx:03d}.flac`，与 `windows.uid` 一一对应。
- DB `flag_sing=1`：**14** 窗（全部纳入试跑样本）：
  `5j651zUx6q4_008, 7uMXWgvf_IU_002, 7uMXWgvf_IU_004, 7uMXWgvf_IU_006, KwklVl7E6Ec_001, TA0W22-E_0M_001, W6q_eMvdJ1Y_004, am5t5f9S3Z8_006, iG1olu8M82U_002, mlNSL9Bt5dw_001, pVn529r5yWc_001, tMvCw-t6-Uc_001, tMvCw-t6-Uc_004, uMm5I9C7MDQ_005`
- 采样：seed=42，先全收 singing 标记，再随机补齐至 50。

## 工具与模型（均 CPU；单文件均 ≪ 2GB）
| 列 | 工具 | 模型路径 | 大小 |
|---|---|---|---|
| music_prob, singing_prob | PANNs Cnn14（inaSpeechSegmenter 因 TF/依赖过重跳过） | `models/Cnn14_mAP=0.431.pth` | ~313 MB |
| snr_db | brouhaha-vad ONNX | `models/brouhaha.onnx` | ~16 MB |
| dnsmos_ovrl | DNSMOS `sig_bak_ovr.onnx` (+p808) | `models/sig_bak_ovr.onnx`, `model_v8.onnx` | ~1.2 MB + 220 KB |

定义见 `scripts/run_window_quality.py` 文档字符串。

## 试跑计时（见 `trial_50_timing.json`）
| 工具 | 秒 | s/窗 | 失败 |
|---|---:|---:|---:|
| PANNs | 7.8 | 0.155 | 0 |
| Brouhaha SNR | 11.6 | 0.233 | 0 |
| DNSMOS OVRL | 38.0 | 0.761 | 0 |
| **合计** | **57.4** | **1.15** | **0** |

外推全量 4911：`est_hours ≈ 1.57 h`。

## 阻塞 / 风险
- 无 >2GB 下载阻塞。
- 机器内存紧张（约 15G，可用 ~3G）；脚本按工具串行加载/释放模型。
- 未改 sqlite / work 音频。

## 下一步
因 est_hours ≤ 12，同一脚本全量跑完并交付 `window_quality.csv` 等。
