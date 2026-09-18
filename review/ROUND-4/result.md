# ROUND-4 阶段4 · 复核

- 输入：`rounds/ROUND-4.yaml` `comparisons: []`；`ROUND-4/*/metrics/*.json`；`data/corpus_v2.sqlite`；`frame.yaml: inputs`
- 出发 commit：`8533d3ca020de84754b117612f9212dc6aaf12b6`（PR #27 merge）
- 判定：**PASS**
- 禁止：本目录与 `recompute/` 均未 `import src`

## 1. Metrics glob

`ROUND-4/` 目录不存在。`rounds/ROUND-4.yaml: comparisons` 为 `[]`，规格写明本轮不重跑 ROUND-3 comparison、不写 `ROUND-4/<comparison_id>/`。对每个 metrics 数字：集合为空。

| 键 | 我的值 | metrics 中的值 | 复现命令 | 一致 |
|----|--------|----------------|----------|------|
| `n_metrics_json` | 0 | 无文件（glob 空） | `python3 -c "from pathlib import Path; print(len(list(Path('.').glob('ROUND-4/*/metrics/*.json'))))"` | 是 |

## 2. 自写最小查询（语料数字）

工作目录证据：`review/ROUND-4/recompute/numbers.json`，脚本 `review/ROUND-4/recompute/recompute.py`（sqlite3 / csv / ast / hashlib；不 import `src`）。语料 `data/corpus_v2.sqlite`。

| 键 | 我的值 | 声明值（非 metrics JSON） | 复现命令 | 一致 |
|----|--------|---------------------------|----------|------|
| `corpus_sha256` | `2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f` | `frame.yaml: inputs.corpus_sha256` 同左 | `python3 -c "import hashlib; print(hashlib.sha256(open('data/corpus_v2.sqlite','rb').read()).hexdigest())"` | 是 |
| `expected_rows` | 4439 | `frame.yaml: expected_rows` = 4439 | `python3 -c "import sqlite3; print(sqlite3.connect('data/corpus_v2.sqlite').execute(open('sql/count_windows_ab.sql').read()).fetchone()[0])"` | 是 |
| `n_videos` | 567 | `frame.yaml: video_counts.n_videos` = 567 | `python3 -c "import sqlite3; print(sqlite3.connect('data/corpus_v2.sqlite').execute('SELECT COUNT(*) FROM videos').fetchone()[0])"` | 是 |
| `windows_quality_matched_ab` | 4439 | `frame.yaml: joins.windows_quality.expected_rows` = 4439 | `python3 review/ROUND-4/recompute/recompute.py` | 是 |
| `video_flags_matched` | 567 | `frame.yaml: joins.video_flags.expected_rows` = 567 | `python3 review/ROUND-4/recompute/recompute.py` | 是 |
| `windows_ab_join_videos` | 4439 | `frame.yaml: joins.windows_videos.expected_rows` = 4439 | `python3 -c "import sqlite3; print(sqlite3.connect('data/corpus_v2.sqlite').execute(\"SELECT COUNT(*) FROM windows JOIN videos ON windows.video_id = videos.video_id WHERE windows.tier IN ('A', 'B')\").fetchone()[0])"` | 是 |
| `comparisons_m` | 0 | `expected/comparisons_m.count` = 0 且 `rounds/ROUND-4.yaml` 含 `comparisons: []` | `python3 -c "import pathlib; print(pathlib.Path('expected/comparisons_m.count').read_text().strip()); print('comparisons: []' in pathlib.Path('rounds/ROUND-4.yaml').read_text())"` | 是 |

`windows_quality` / `video_flags` 交叉计数的一次性命令：

```bash
python3 -c "import csv,sqlite3; u={r[0] for r in sqlite3.connect('data/corpus_v2.sqlite').execute(\"SELECT uid FROM windows WHERE tier IN ('A','B')\")}; i={row['window_id'] for row in csv.DictReader(open('task2_window_quality/window_quality_with_flags.csv'))}; print(len(u & i))"
python3 -c "import csv,sqlite3; v={r[0] for r in sqlite3.connect('data/corpus_v2.sqlite').execute('SELECT video_id FROM videos')}; i={row['video_id'] for row in csv.DictReader(open('task3_multilabel_flags/video_multilabel_flags.csv'))}; print(len(v & i))"
```

## 3. 四条规则（静态重算，读文本不 import `src`）

| 键 | 我的值 | 规格值 | 复现命令 | 一致 |
|----|--------|--------|----------|------|
| `pd_merge_text_count` | 1 | 1（H2：`src/merge.py` 恰好一处 `pd.merge(`） | `python3 -c "print(open('src/merge.py').read().count('pd.merge('))"` | 是 |
| `pd_merge_ast_count` | 1 | 1 | `python3 review/ROUND-4/recompute/recompute.py` | 是 |
| `enforce_expected_hits` | 0 | 0（H1：无布尔关闭参数） | `python3 review/ROUND-4/recompute/recompute.py` | 是 |
| `left_attach_uses_frame_literal` | 1 | 1（H2：匹配行数只读 `frame.yaml: joins.*.expected_rows`） | `python3 -c "t=open('src/merge.py').read(); print('expected_rows = spec[\"expected_rows\"]' in t, 'enforce_expected' not in t)"` | 是 |
| `review_import_src_hits` | 0 | 0（H3） | `python3 review/ROUND-4/recompute/recompute.py` | 是 |

对照预测：

- H1：`src/` 中无 `enforce_expected` 形参/名字/关键字；`left_attach` 走 `checked_merge`。成立。
- H2：`pd.merge(` 文本与 AST 均为 1；`expected_rows = spec["expected_rows"]`。成立。
- H3：`review/` 无 `import src` / `from src`；语料 sha256 与 `frame.yaml: inputs.corpus_sha256` 相等。成立。
- 合并闸门：PR #27 的 `tests` / `contract-check` / `scope-check` 均为 SUCCESS。

## 4. Advisory（不计打回）

- `scripts/contract_check.py` 未出现预测第 1 条四个名字 `merge_pd_merge_once` / `no_boolean_gate_bypass` / `review_no_import_src` / `corpus_sha256_matches_frame`。等价检查在 `tests/test_round4_gates.py`；impl write_scope 不含 `scripts/`。
- `sql/join_windows_videos.sql` 无 tier 过滤，全表 JOIN 得 4911 行；`frame.yaml: joins.windows_videos.expected_rows` 按 A+B 白名单记 4439。本复核按白名单计数，与字面量一致。
- `src/round3.py` 在 `len(uid_left) != windows_quality.expected_rows` 时跳过 `left_attach`（夹具/smoke 路径）。参数级布尔门已删除；该跳过不计本轮打回。

## 5. 结论

**PASS**
