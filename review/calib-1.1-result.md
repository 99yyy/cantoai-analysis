# 复核 · 一.1 calib demucs var_db（阶段4）

- 交付路径：`analysis/task_calib_demucs_var/`
- 本地绝对路径：`/workspace/cantoai/analysis/task_calib_demucs_var/`
- 结果 commit：工作区 `/workspace/cantoai` 为 `4804b53`；分析仓库 `99yyy/cantoai-analysis` 对应推送为 `42f5ae9`（内容等价，两库历史不同）
- 判定：**通过**
- 说明：校准期一.1 按 LOOP「旧派单收口」；本文件为阶段4复核记录

## 独立重算（未 import / 未执行对方主脚本）

```bash
/workspace/cantoai/.venv/bin/python - <<'PY'
import json
from pathlib import Path
import numpy as np
import pandas as pd
root = Path('/workspace/cantoai/analysis/task_calib_demucs_var')
df = pd.read_csv(root / 'window_var_db.csv')
mask = (df.rms_vocals > 0) & (df.rms_rest > 0)
recalc = 20 * np.log10(
    df.loc[mask, 'rms_vocals'].to_numpy(float)
    / df.loc[mask, 'rms_rest'].to_numpy(float)
)
diff = np.abs(recalc - df.loc[mask, 'var_db'].to_numpy(float))
vd = df.loc[mask, 'var_db']
flac = len(list(Path('/workspace/cantoai/corpus/dataset_v2/work/windows').glob('*.flac')))
ft = json.loads((root / 'full_timing.json').read_text())
print(len(df), int(df.demucs_ok.sum()), int((df.demucs_ok != 1).sum()), flac)
print(float(diff.max()), float(vd.mean()), float(vd.median()))
print(float(vd.quantile(0.25)), float(vd.quantile(0.75)), float(vd.quantile(0.1)), float(vd.quantile(0.9)))
print(ft['elapsed_hours'], ft['weight_bytes'], ft['failures'])
PY
```

| 检查项 | 独立结果 | 交付声称 | 一致 |
|--------|----------|----------|------|
| 行数 | 4911 | 4911 | 是 |
| `demucs_ok==1` | 4911 | 4911 | 是 |
| 失败行 | 0 | 0 | 是 |
| FLAC 覆盖 | 4911 / 4911，无缺失无多余 | 4911 窗 | 是 |
| `var_db` 相对 `20*log10(rms_vocals/rms_rest)` 的 max\|Δ\| | 5.0e-05 | 定义一致 | 是（\<1e-3） |
| mean / median | 17.9774 / 12.7168 | 17.98 / 12.72 | 是 |
| p25 / p75 | 7.1415 / 25.0572 | 7.14 / 25.06 | 是 |
| p10 / p90 | 4.7808 / 42.8119 | 4.78 / 42.81 | 是 |
| 墙钟小时 | 4.4922 | ≈4.49 h | 是 |
| 权重字节（JSON + 磁盘） | 84025440 | 84025440（80.13 MB） | 是 |
| 权重 >2GB | false | false | 是 |

## 可验证通过条件（硬）

1. `wc -l analysis/task_calib_demucs_var/window_var_db.csv` → **4912**（含表头），且 `demucs_ok` 全为 1。
2. 上节独立片段中 `max|Δvar_db| < 1e-3`，且 mean/median 与 README 四舍五入到小数第二位一致。
3. `full_timing.json` 中 `failures==0` 且 `weight_bytes==84025440`。

本次均已满足。

## 替代解释（≥2）

1. **Demucs 人声泄漏**：弦乐/合唱/混响可进 vocals，抬高 `rms_vocals`，`var_db` 偏大 ≠「对白主导」。
2. **短窗不稳**：数秒窗分离相位/瞬态不稳，邻窗可跳十余 dB，全库均值对单窗解释力有限。
3. **rest 定义**：`drums+bass+other` 加和并非真实非人声；对白混响进 other 会压低 `var_db`。
4. **与 Brouhaha `snr_db` 不可互换**：后者训练几乎剔除音乐噪声，不能把 `var_db` 直接读成清晰度。

## advisory（不计入硬条件）

- fyp 消息中的 `42f5ae9` 本仓库不存在；结果提交为 `4804b53`。
- README 注明本机 numpy 可能与 `requirements.txt` 的 `<2` 约束不一致；不影响本 CSV 数值复核。
- 本交付无分布图；作后续阈值论证时建议补直方图（advisory）。

## 结论

**通过。** 一.1 可收口；关键数字有独立最小查询支撑，未见无 CSV/计时 JSON 支撑的关键声称。
