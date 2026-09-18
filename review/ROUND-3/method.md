# ROUND-3 阶段1 · 方法审

- 输入：`rounds/ROUND-3.md` + `rounds/ROUND-3.yaml`（方法审打回计数 1/2）
- 判定：**改**
- 对照：工具适用 / 判据可重算 / 预测写死 / 脚本契约；以及派单硬约束（不重跑推断、阶段2仅脚手架、阶段3等合入、不碰 dataset、契约 sha256）

## 已核对（可保留）

- 问题可证伪；H1–H3 有数值门槛；预测三不等式已写；冻结规则明确。
- **不重跑模型推断**、阶段2仅脚手架且禁止统计数字、阶段3等阶段2合入、不动 dataset repo：正文已钉死，符合派单硬约束。
- 五条「已核实事实」本机抽查：
  - `windows` 28 列无 `music_prob/singing_prob/snr_db/dnsmos_ovrl`：是。
  - `flag_sing=1` 仅 14 且全 tier C：是。
  - PANNs `singing_prob≥0.5 ∧ flag_sing=0`：13 条，A6/C7，6 视频，其中 dur>10 为 8：与文一致。
  - dur>10：2142（A+B 2006）；中位 dur≈7.93：一致。
  - 基数 4911/567、tier A/B/C：一致。
- `ROUND-3.yaml` 声明 `baseline_model`、`comparisons`（m=3）、`pairable_span_predicate`、`audio_span_provenance`、`barred_stratifiers`：方向正确。

## 硬条件（必须全部满足才复审通过）

### 1. 契约文件可核验

**现状**：工作区无 `.cursor/rules/analysis-contract.mdc`；`git` 无对象 `226c78a`；无法对 sha256 `461e8928597b1269be05088f3296663b896f1a5c4d264c2d7be3cf41ad5db3e5` 做 `sha256sum` 核对。

**通过条件**：

```bash
test -f /workspace/cantoai/analysis/.cursor/rules/analysis-contract.mdc
sha256sum /workspace/cantoai/analysis/.cursor/rules/analysis-contract.mdc \
  | awk '{exit !($1=="461e8928597b1269be05088f3296663b896f1a5c4d264c2d7be3cf41ad5db3e5")}'
```

（若路径/hash 变更，ROUND 元数据与上式同步改到可核验值。）

### 2. 钉死 H2/H3 的 `singing_prob` 来源（禁止与事实4矛盾）

事实4已声明 CLAP 前10s 与 PANNs 整窗**不得同列比较**，但 H2/H3 仍写裸名 `singing_prob`。

**通过条件**：`ROUND-3.md` + `ROUND-3.yaml` 对 H2/H3 **显式写死其一**（推荐）：

- 使用 `analysis/task2_window_quality/window_quality_with_flags.csv` 的 `singing_prob`（整窗 PANNs），并写明 H2/H3 **不**与 CLAP `clap_sing` 同表；或
- 使用 `analysis/ROUND-1/window_clap_sing.csv` 的 `clap_sing`，且子集强制 `windows.dur <= 10`。

禁止继续使用未限定来源的裸名 `singing_prob`。

### 3. 统一 H3 阈值符号

**现状**：`ROUND-3.md` 预测为 `delta_pp ≤ 0.5`（单向）；`ROUND-3.yaml` 为 `abs(delta_pp) <= 0.5`。

**通过条件**：两处改为同一不等式（选定单向或绝对值），且与 `metrics/singing_removal.json` 键语义一致。

### 4. 脚本契约钉死复用输入路径

**通过条件**：`ROUND-3.md` 脚本契约列出只读输入（CLI 无默认值亦可，但须有名字），至少：

- corpus sqlite
- `window_quality_with_flags.csv`（含 `singing_prob`,`snr_db`）
- `window_clap_sing.csv`（若 H2/H3 不用可标「本轮不读」）
- syllables / jp_match 来源表
- `ROUND-3.yaml`、`frame.yaml`

并写明：**禁止**调用任何推理入口（无 `run_clap*` / `run_*panns*` / demucs 推理）。

### 5. 预测 commit 在阶段2 launch 前可 `rev-parse`

**通过条件**：元数据 `预测 commit` 非空，且

```bash
git -C <analysis-clone> rev-parse --verify <预测commit>^{commit}
```

退出码 0；该 commit 含冻结后的预测三不等式；早于任何结果 commit。

## advisory（不阻塞）

- 阶段2冒烟：建议 `python -m src.round3 --check-frame`（或等价）只校验 schema/`checks.json`，不写 metrics 数字；可在复修时一并写入契约。
- 事实3的 13 条作抽听清单：与「不据 singing_prob 下阈值」一致，保持即可。
- 音频员仅补 `t0_s/t1_s`：已写清，保留。

## 结论

**改。** 满足硬条件 1–5 后改 ROUND 并再派阶段1复审；计数 1/2。在此之前不得 launch 阶段2。
