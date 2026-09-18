# audit.py 审稿（对照 `docs/AUDIT-SPEC.md`）

- 输入：`scripts/audit.py` + `docs/AUDIT-SPEC.md`（PR #8；路径发现已复修）
- 判定：**通过**
- 库：`/workspace/cantoai/corpus/dataset_v2/work/corpus.sqlite`（只读）
- 表：`analysis/ROUND-2/listening_sheet.csv`
- 重算：`review/audit/recalc_key.json`
- 复审：2026-09-18（硬条件 1–2 已满足）

## 关键断言独立重算（C3 / C4 / L2 / R1 / R2）

自写 sqlite3/csv（不 import `audit` 检查函数）；与 audit 实测一致：

| ID | 规格 2026-09-18 | 独立重算 | audit（`ICANTO_ROOT=/workspace/cantoai`） | 期望语义 |
|----|-----------------|----------|------------------------------------------|----------|
| C3 | 2183 | **2183** | FAIL `empty_or_none=2183` | ==0 → 必须 FAIL |
| C4 | 23860 | **23860** | FAIL `dur_le_0=23860` | ==0 → 必须 FAIL |
| L2 | max=410 | **410** | FAIL `max_text_clean_in_A=410` | ≤2 → 必须 FAIL |
| R1 | 42/200 | **42**/200 | FAIL `tier_not_AB=42/200` | ==0 → 必须 FAIL |
| R2 | 32/200 | **32**/200 | FAIL `lang_not_yue=32/200` | ==0 → 必须 FAIL |

未改期望洗绿；退出码非零。

## 硬条件复核

### 1. monorepo 根 discover 不得读 fixtures — **满足**

```text
common_py = …/corpus/dataset_v2/scripts/common.py
stats     = …/corpus/dataset_v2/dataset_v2/STATS.json
sqlite    = …/corpus/dataset_v2/work/corpus.sqlite
```

路径均不含 `fixtures`。

### 2. 规格示例原样可跑 — **满足**

`ICANTO_ROOT=/workspace/cantoai ANALYSIS_ROOT=…/analysis python3 scripts/audit.py --round 2`

- 退出码 1
- C3/C4/L2/R1/R2 数量级同上且 FAIL
- `PASS C1 … via=imported:…/corpus/dataset_v2/scripts/common.py`（无 fixtures）

## advisory

- 仅标准库、只读 sqlite：满足。
- R1/R2 FAIL 与抽样框已知偏差一致，应保持 FAIL。
- R5 因分析库无 `.git` 为 SKIP，可接受。
- SUMMARY 仍有其他 FAIL（规格预期的已知债）；本审只钉死路径发现 + 五条关键数量级。

## 结论

**通过。** 路径发现修复有效；关键五条数量级正确且正确 FAIL。可收。
